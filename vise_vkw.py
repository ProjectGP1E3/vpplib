# -*- coding: utf-8 -*-
"""
Created on Tue Jan 28 15:35:09 2020

Generate a virtual power plant based on predefined numbers of buses and
components.

Export timeseries and component values to csv-files at the end

@author: pyosch
"""

import pandas as pd
import random
import time
import pickle
from tqdm import tqdm
import copy

import simbench as sb
import pandapower as pp

from vpplib import VirtualPowerPlant, UserProfile, Environment, Operator
from vpplib import Photovoltaic, WindPower, BatteryElectricVehicle
from vpplib import HeatPump, ThermalEnergyStorage, ElectricalEnergyStorage
from vpplib import CombinedHeatAndPower

# define virtual power plant
# pv_number = 100
wind_number = 10
bev_number = 50
# hp_number = 50  # always includes thermal energy storage
# ees_number = 80
# chp_number = 0  # always includes thermal energy storage

# component_number = pv_number + bev_number + hp_number + chp_number

# Simbench Network parameters
sb_code = "1-LV-semiurb4--0-sw" #"1-MVLV-semiurb-all-0-sw" # "1-MVLV-semiurb-5.220-0-sw" # 

# Values for environment
start = "2015-01-01 00:00:00"
end = "2015-01-01 23:45:00"
year = "2015"
time_freq = "15 min"
index_year = pd.date_range(
    start=year, periods=35040, freq=time_freq, name="time"
)
index_hours = pd.date_range(start=start, end=end, freq="h", name="time")
timebase = 15  # for calculations from kW to kWh
timezone="Europe/Berlin"

# WindTurbine data
wea_list = [
        "E-53/800",
        "E48/800",
        "V100/1800",
        "E-82/2000",
        "V90/2000"]  # randomly choose windturbine
hub_height = 135
rotor_diameter = 127
fetch_curve = "power_curve"
data_source = "oedb"

# Wind ModelChain data
# possible wind_speed_model: 'logarithmic', 'hellman',
# 'interpolation_extrapolation', 'log_interpolation_extrapolation'
wind_speed_model = "logarithmic"
density_model = "ideal_gas"
temperature_model = "linear_gradient"
power_output_model = "power_coefficient_curve"  # alt.: 'power_curve'
density_correction = True
obstacle_height = 0
hellman_exp = None


# Values for bev
# power and capacity will be randomly assigned during component generation
battery_min = 4
battery_usage = 1
bev_charge_efficiency = 0.98
load_degradation_begin = 0.8

#%% load dicts with electrical and thermal profiles
with open(r'Results/20200528_up_dummy_profiles.pickle', 'rb') as handle:
    household_dict = pickle.load(handle)

print(time.asctime( time.localtime(time.time()) ))
print("Loaded input\n")


#%% Adjust the values of the environments in the household_dict with the
#   current values. Since the environment is stored in one place
#   (eg. 0x158c9b24c08) and all components have the same, it only has to be
#   changed once!

household_dict[list(household_dict.keys())[0]].environment.start = start
household_dict[list(household_dict.keys())[0]].environment.end = end
household_dict[list(household_dict.keys())[0]].environment.timebase = timebase
household_dict[list(household_dict.keys())[0]].environment.timezone = timezone
household_dict[list(household_dict.keys())[0]].environment.year = year
household_dict[list(household_dict.keys())[0]].environment.time_freq = time_freq

# get data for timeseries calculations
household_dict[list(household_dict.keys())[0]].environment.get_mean_temp_days()
household_dict[list(household_dict.keys())[0]].environment.get_mean_temp_hours()
household_dict[list(household_dict.keys())[0]].environment.get_pv_data()
household_dict[list(household_dict.keys())[0]].environment.get_wind_data()

#%% Get timeseries of the households

for house in household_dict.keys():
    if "pv_system" in list(household_dict[house].__dict__.keys()):
        household_dict[house].pv_system.prepare_time_series()
        
        # TODO
        # Somehow in some pvlib timeseries the inverter losses during night hours
        # are not complete. Once we find out how to solve this problem we can
        # delete this part:
        if household_dict[house].pv_system.timeseries.isnull().values.any():
                household_dict[house].pv_system.timeseries.fillna(
                    value=0,
                    inplace=True)

# %% virtual power plant

vpp = VirtualPowerPlant("vpp")

# %% Simbench network

net = sb.get_simbench_net(sb_code)

# plot the grid
pp.plotting.simple_plot(net)

# drop preconfigured electricity generators  and loads from the grid
net.sgen.drop(net.sgen.index, inplace = True)
net.load.drop(net.load.index, inplace = True)

print(time.asctime(time.localtime(time.time())))
print("Initialized environment, vpp and net\n")


#%% Assign user_profiles to buses
up_dict = dict()
for bus in tqdm(net.bus.name):
    if "LV" in bus:

        house = random.sample(household_dict.keys(), 1)[0]
        up_id = bus+'_'+house

        # In this place we need a deep copy to recieve independent users.
        # Otherwise changes in one up would impact multiple up's
        up_dict[up_id] = copy.deepcopy(household_dict[house])
        up_dict[up_id].bus = bus

        # Adjust the identifier of the user_profile itself
        up_dict[up_id].identifier = up_id

        # Adjust the identifier of the components
        # Add components to vpp and pandapower network
        if "pv_system" in up_dict[up_id].__dict__.keys():
            up_dict[up_id].pv_system.identifier = up_id+'_pv'

            vpp.add_component(up_dict[up_id].pv_system)

            pp.create_sgen(
                net,
                bus=net.bus[net.bus.name == bus].index[0],
                p_mw=(
                    vpp.components[up_id + "_pv"].module.Impo
                    * vpp.components[up_id + "_pv"].module.Vmpo
                    / 1000000
                ),
                q_mvar = 0,
                name=(up_id + "_pv"),
                type="pv",
            )

        if "chp" in up_dict[up_id].__dict__.keys():
            up_dict[up_id].chp.identifier = up_id+'_chp'
            vpp.add_component(up_dict[up_id].chp)
            
            pp.create_sgen(
                net,
                bus=net.bus[net.bus.name == bus].index[0],
                p_mw=(vpp.components[up_id + "_chp"].el_power / 1000),
                q_mvar = 0,
                name=(up_id + "_chp"),
                type="chp",
            )

        if "hr" in up_dict[up_id].__dict__.keys():
            up_dict[up_id].hr.identifier = up_id+'_hr'
            vpp.add_component(up_dict[up_id].hr)
            
            pp.create_load(
                net,
                bus=net.bus[net.bus.name == bus].index[0],
                p_mw=(vpp.components[up_id + "_hr"].el_power / 1000),
                q_mvar = 0,
                name=(up_id + "_hr"),
                type="hr",
            )

        if "hp" in up_dict[up_id].__dict__.keys():
            up_dict[up_id].hp.identifier = up_id+'_hp'
            vpp.add_component(up_dict[up_id].hp)
            
            pp.create_load(
                net,
                bus=net.bus[net.bus.name == bus].index[0],
                p_mw=(vpp.components[up_id + "_hp"].el_power / 1000),
                q_mvar = 0,
                name=(up_id + "_hp"),
                type="hp",
            )

        if "tes" in up_dict[up_id].__dict__.keys():
            up_dict[up_id].tes.identifier = up_id+'_tes'
            vpp.add_component(up_dict[up_id].tes)
            # Thermal component, no equivalent in pandapower

        if "ees" in up_dict[up_id].__dict__.keys():
            up_dict[up_id].ees.identifier = up_id+'_ees'

            vpp.add_component(up_dict[up_id].ees)

            pp.create_storage(
                net,
                bus=net.bus[net.bus.name == bus].index[0],
                p_mw=0,
                q_mvar = 0,
                max_e_mwh=vpp.components[up_id + "_ees"].capacity / 1000,
                name=(up_id + "_ees"),
                type="ees",
            )

        if "bev" in up_dict[up_id].__dict__.keys():
            up_dict[up_id].bev.identifier = up_id+'_bev'

            vpp.add_component(up_dict[up_id].bev)
            
            pp.create_load(
                net,
                bus=net.bus[net.bus.name == bus].index[0],
                p_mw=(vpp.components[up_id + "_bev"].charging_power / 1000),
                q_mvar = 0,
                name=(up_id + "_bev"),
                type="bev",
            )


# %% generate user profiles based on grid buses for mv

# if wind_number > 0:
#     mv_buses = []

#     for bus in net.bus.name:
#         if "MV" in bus:
#             mv_buses.append(bus)

# count = 0
# up_with_wind = []
# while count < wind_number:

#     simbus = random.sample(mv_buses, 1)[0]
#     vpp.buses_with_wind.append(simbus)

#     user_profile = UserProfile(
#         identifier=simbus,
#         latitude=latitude,
#         longitude=longitude,
#         thermal_energy_demand_yearly=yearly_thermal_energy_demand,
#         building_type=building_type,
#         comfort_factor=None,
#         t_0=t_0,
#         daily_vehicle_usage=None,
#         week_trip_start=[],
#         week_trip_end=[],
#         weekend_trip_start=[],
#         weekend_trip_end=[],
#     )

#     #TODO: MAYBE USE FOR aggregated MV loads
#     # Uncomment if loadprofile in user_profile is needed
#     # Keep in mind to include check for loadprofile when choosing "simbus"
#     # like done for lv_buses.
#     #
#     # user_profile.baseload = pd.DataFrame(
#     #     profiles['load', 'p_mw'][
#     #         net.load[net.load.bus == net.bus[
#     #             net.bus.name == simbus].index.item()].iloc[0].name
#     #         ].loc[start:end]
#     #     * 1000)
#     # # thermal energy demand equals two times the electrical energy demand:
#     # user_profile.thermal_energy_demand_yearly = (user_profile.baseload.sum()
#     #                                              / 2).item()  # /4 *2= /2
#     # user_profile.get_thermal_energy_demand()

#     up_with_wind.append(user_profile.identifier)

#     up_dict[user_profile.identifier] = user_profile
#     count += 1

# # create a list of all user profiles and shuffle that list to obtain a random
# # assignment of components to the bus
# up_list = list(up_dict.keys())
# random.shuffle(up_list)

print(time.asctime(time.localtime(time.time())))
print("Generated user_profiles\n")


# %% generate wea

for bus in vpp.buses_with_wind:

    new_component = WindPower(
    unit="kW",
    identifier=(bus + "_wea"),
    environment=environment,
    user_profile=None,
    turbine_type=wea_list[random.randint(0, (len(wea_list) -1))],
    hub_height=hub_height,
    rotor_diameter=rotor_diameter,
    fetch_curve=fetch_curve,
    data_source=data_source,
    wind_speed_model=wind_speed_model,
    density_model=density_model,
    temperature_model=temperature_model,
    power_output_model=power_output_model,
    density_correction=density_correction,
    obstacle_height=obstacle_height,
    hellman_exp=hellman_exp,
    )
    new_component.prepare_time_series()
    vpp.add_component(new_component)

# %% generate bev

for bus in vpp.buses_with_bev:

    new_component = BatteryElectricVehicle(
    unit="kW",
    identifier=(bus + "_bev"),
    battery_max=random.sample([50, 60, 17.6, 64, 33.5, 38.3,75, 20, 27.2, 6.1]
                              , 1)[0],
    battery_min=battery_min,
    battery_usage=battery_usage,
    charging_power=random.sample([3.6, 11, 22], 1)[0],
    charge_efficiency=bev_charge_efficiency,
    environment=environment,
    user_profile=up_dict[bus],
    load_degradation_begin=load_degradation_begin,
    )

    new_component.prepare_time_series()
    vpp.add_component(new_component)



print(time.asctime(time.localtime(time.time())))
print("Generated components in vpp\n")

# %% initialize operator

operator = Operator(virtual_power_plant=vpp,
                    net=net,
                    target_data=None,
                    environment=environment)

print(time.asctime(time.localtime(time.time())))
print("Initialized Operator\n")

# %% timeseries are in kW, pandapower needs MW
for component in vpp.components.keys():
    # el energy storage does not have a timeseries yet
    if "_ees" not in component:
        vpp.components[component].timeseries /= 1000

# %% run base_scenario without operation strategies
net_dict = operator.run_vise_scenario(el_dict)

print(time.asctime(time.localtime(time.time())))
print("Finished run_simbench_scenario()\n")
# %% extract results from powerflow

results = operator.extract_results(net_dict)
single_result = operator.extract_single_result(
    net_dict, res="ext_grid", value="p_mw"
)

print(time.asctime(time.localtime(time.time())))
print("Exported results\n")
# %% plot results of powerflow and storage values

# single_result.plot(
#     figsize=(16, 9), title="ext_grid from single_result function"
# )
# operator.plot_results(results, legend=False)
# operator.plot_storages()