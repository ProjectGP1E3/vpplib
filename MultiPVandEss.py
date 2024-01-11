from torch import t
from vpplib.user_profile import UserProfile
from vpplib.environment import Environment
from vpplib.electrical_energy_storage import ElectricalEnergyStorage
from vpplib.photovoltaic import Photovoltaic

from vpplib.heat_pump import HeatPump
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import gurobipy as gp
from gurobipy import GRB


# Values for environment
start = "2015-05-01 12:00:00"
end = "2015-05-01 23:45:00"
year = "2015"
time_freq = "15 min"
timestamp_int = 48
timestamp_str = "2015-01-01 12:00:00"
timebase = 15

#values for time interval
num_hours=1*24
time_step_size=15
num_time_step=int(num_hours*60//time_step_size)

# Values for user_profile
latitude = 50.941357
longitude = 6.958307
building_type = "DE_HEF33"
t_0 = 40

# PV
unit = "kW"
name = "PVbus"
module_lib = "SandiaMod"
module = "Canadian_Solar_CS5P_220M___2009_"
inverter_lib = "cecinverter"
inverter = "Connect_Renewable_Energy__CE_4000__240V_"
surface_tilt = 20
surface_azimuth = 200
modules_per_string = 4
strings_per_inverter = 2
temp_lib = 'sapm'
temp_model = 'open_rack_glass_glass'

# initialisation of enviroment 
environment = Environment(
    timebase=timebase, start=start, end=end, year=year, time_freq=time_freq
)
environment.get_pv_data(file="./input/pv/dwd_pv_data_2015.csv")
#initialisation of user profile 
user_profile = UserProfile(
    identifier=name,
    latitude=latitude,
    longitude=longitude,
    building_type=building_type,
    comfort_factor=None,
    t_0=t_0,
)

pv = Photovoltaic(
    unit=unit,
    identifier=(name + "_pv"),
    environment=environment,
    user_profile=user_profile,
    module_lib=module_lib,
    module=module,
    inverter_lib=inverter_lib,
    inverter=inverter,
    surface_tilt=surface_tilt,
    surface_azimuth=surface_azimuth,
    modules_per_string=modules_per_string,
    strings_per_inverter=strings_per_inverter,
    temp_lib=temp_lib,
    temp_model=temp_model
)
pv.prepare_time_series()

# Battery Variables Initialization
maxChargingPower=0.05
maxDischargingPower=0.04
dischargingEfficiency=0.98
chargingEfficiency=0.98
minimumCharge=0
maximumCharge=4
max_power = 4  # kW
capacity = 4  # kWh
max_c = 1
timebase = 15


# Getting Prices 
prices = environment.get_price_data()
pvPower=pv.timeseries.loc[start:end] #type: ignore

# creating an ESS
ESS = ElectricalEnergyStorage(
    unit=unit,
    identifier=(name + "_storage"),
    environment=environment,
    user_profile=user_profile,
    capacity=capacity,
    charge_efficiency=chargingEfficiency,
    discharge_efficiency=dischargingEfficiency,
    max_power=max_power,
    max_c=max_c,
)

# defining variables
timestep=15
T=num_time_step
set_T = range(0,T-1)

prices_use=prices.iloc[0:num_hours, 0].values
pvPower_use=pvPower.iloc[0:num_hours,0].values
pvPower_use[pvPower_use < 0]=0

# Create models
m = gp.Model('MIP')
m.setParam('TimeLimit',5*60)

pricesModel = {t: prices_use[(t *time_step_size)//60] for t in set_T}
pvPowerModel= {t: pvPower_use[(t *time_step_size)//60] for t in set_T}
chargingPower = {t:m.addVar(vtype=GRB.CONTINUOUS,lb=0,ub=maxChargingPower,name="chargingPower_{}".format(t)) for t in set_T}
dischargingPower = {t:m.addVar(vtype=GRB.CONTINUOUS,lb=0,ub=maxDischargingPower,name="dischargingPower_{}".format(t)) for t in set_T}
chargingState = {t:m.addVar(vtype=GRB.INTEGER,lb=0,ub=1,name="chargingState_{}".format(t)) for t in set_T}
dischargingState = {t:m.addVar(vtype=GRB.INTEGER ,lb=0,ub=1,name="dischargingState_{}".format(t)) for t in set_T}
charge={t:m.addVar(vtype=GRB.CONTINUOUS,lb=minimumCharge,ub=maximumCharge ,name="chargePercentage_{}".format(t)) for t in set_T}

#Constraints on charging process

#chargingPower constraints
constraints_eq1={t: m.addConstr(lhs = chargingPower[t],sense = GRB.LESS_EQUAL,rhs= chargingState[t] * maxChargingPower ,name='chargingPower_constraint_{}'.format(t)) for t in set_T} # type: ignore 
#state of charge constraint
constraints_eq2={t: m.addConstr(lhs = charge[t-1] + chargingEfficiency*timestep*chargingPower[t],sense = GRB.LESS_EQUAL,rhs= maximumCharge,name='chargingState_constraint_{}'.format(t)) for t in range(1,T-1)} # type: ignore

#Constraints on discharging process

#chargingPower constraints
constraints_eq3={t: m.addConstr(lhs = dischargingPower[t],sense = GRB.LESS_EQUAL,rhs= dischargingState[t] * maxDischargingPower ,name='dischargingPower_constraint_{}'.format(t)) for t in set_T} # type: ignore
#state of charge constraint
constraints_eq4={t: m.addConstr(lhs = charge[t-1] - (1/dischargingEfficiency)*timestep*dischargingPower[t],sense = GRB.GREATER_EQUAL,rhs= minimumCharge ,name='dischargingState_constraint_{}'.format(t)) for t in range(1,T-1)} # type: ignore

#Constraints on Processes
constraints_eq5={t: m.addConstr(lhs = chargingState[t]+dischargingState[t],sense = GRB.LESS_EQUAL,rhs= 1 ,name='chargingDischargingCorrelation_constraint_{}'.format(t)) for t in set_T} # type: ignore

#Constraints on Charge
constraints_eq6=   {t: m.addConstr(lhs=charge[t] ,sense = GRB.EQUAL,rhs= charge[t-1]+chargingEfficiency*timestep*chargingPower[t]-timestep*dischargingEfficiency*dischargingPower[t],name='charge_constraint_{}'.format(t)) for t in range(1,T-1)} # type: ignore
constraints_eq6[0]=    m.addConstr(lhs=charge[0] ,sense = GRB.EQUAL,rhs= 0,name='charge_constraint_{}'.format(0)) # type: ignore

#PV incorporation
constraints_eq7={t: m.addConstr(lhs = chargingPower[t],sense = GRB.LESS_EQUAL,rhs= pvPowerModel[t] ,name='chargingPowerPV_constraint_{}'.format(t)) for t in set_T} # type: ignore

#Objective function
objective = gp.quicksum(-1 * chargingPower[t] * timestep * prices.iloc[t, 0] + dischargingPower[t] * timestep * prices.iloc[t, 0] for t in set_T) # type: ignore

m.ModelSense = GRB.MAXIMIZE
m.setObjective(objective)
 # Solve the optimization problem
m.optimize()

# Extracting timeseries
charging_power_values = [chargingPower[t].X for t in set_T]
discharging_power_values = [dischargingPower[t].X for t in set_T]
charge_percentage_values = [charge[t].X for t in range(1, T-1)]  # Starting from 1 because we don't have charge[0]
residualLoad=result = [a - b for a, b in zip(charging_power_values,discharging_power_values)]
time_steps = list(set_T)
if len(charge_percentage_values) < len(time_steps):
    charge_percentage_values.insert(0, 0) 

#prices and discharging
fig, ax1 = plt.subplots(figsize=(10, 5))

# Plotting prices on the primary y-axis
ax1.plot(list(pricesModel.keys()), list(pricesModel.values()), label='Prices', color='b')
ax1.set_ylabel('Prices', color='b')
ax1.tick_params(axis='y', labelcolor='b')

# Creating a secondary y-axis for discharging power
ax2 = ax1.twinx()  
ax2.plot(discharging_power_values, label='Discharging Power', color='g')
ax2.set_ylabel('Discharging Power', color='g')
ax2.tick_params(axis='y', labelcolor='g')

# Adding legend
ax1.legend(loc='upper left')
ax2.legend(loc='upper right')

# Display the plot
plt.show()

#Plots on same axis charging, discharging, SOC
fig, ax1 = plt.subplots(figsize=(12, 6))

discharging_power_values = [-value for value in discharging_power_values]

# Plotting Charging Power as positive bars
ax1.bar(time_steps, charging_power_values, width=0.4, label='Charging Power', color='blue')

# Plotting Discharging Power as negative bars
ax1.bar(time_steps, discharging_power_values, width=0.4, label='Discharging Power', color='orange')

# Creating a secondary y-axis for the SOC
ax2 = ax1.twinx()

# Plotting the SOC on the secondary y-axis
if len(charge_percentage_values) < len(time_steps):
    charge_percentage_values.insert(0, 0)  # Assuming the initial SOC is 0
ax2.plot(time_steps, charge_percentage_values, label='SOC', color='black', linestyle='-')

# Adding labels, title, and grid
ax1.set_xlabel('Time Step')
ax1.set_ylabel('Power (kW)', color='blue')
ax2.set_ylabel('SOC', color='black')
plt.title('Charging/Discharging Power and SOC over Time')
ax1.grid(True)

# Adding legends
ax1.legend(loc='upper left')
ax2.legend(loc='upper right')

# Making the y-axis label color match the data
ax1.tick_params(axis='y', labelcolor='blue')
ax2.tick_params(axis='y', labelcolor='black')

plt.show()

#pv anc charging
fig, ax3 = plt.subplots(figsize=(10, 5))

# Plotting prices on the primary y-axis
ax3.plot(list(pvPowerModel.keys()), list(pvPowerModel.values()), label='PV', color='b')
ax3.set_ylabel('PV', color='b')
ax3.tick_params(axis='y', labelcolor='b')

# Creating a secondary y-axis for discharging power
ax4 = ax3.twinx()  
ax4.plot(charging_power_values, label='Charging Power', color='g')
ax4.set_ylabel('Charging Power', color='g')
ax4.tick_params(axis='y', labelcolor='g')

# Adding legend
ax3.legend(loc='upper left')
ax4.legend(loc='upper right')

# Display the plot
plt.show()

#Dataframe of obtained timeseries
data = {
    'Time Step': time_steps,
    'Charging Power (kW)': charging_power_values,
    'Discharging Power (kW)': [-value for value in discharging_power_values],  # ensure these are negative
    'SOC': charge_percentage_values,
    'Prices': list(pricesModel.values()),
    'PV': list(pvPowerModel.values())
}

df = pd.DataFrame(data)

print(df.head())
print(df.tail())

df = df.set_index('Time Step')