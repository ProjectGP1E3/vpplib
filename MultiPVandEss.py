from matplotlib import style
from matplotlib.lines import drawStyles, lineStyles
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
number_of_days=1
year = "2015"
time_freq = "15 min"
timestamp_int = 48
timebase = 15

#values for time interval
num_hours=number_of_days*24
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
maxChargingPower=0.1
maxDischargingPower=0.09
dischargingEfficiency=0.9
chargingEfficiency=0.9
minimumSoC=5
maximumSoC=40
startSoC=10
max_power = 40 # kW
capacity = 40  # kWh
max_c = 1
timebase = 15


# Getting Prices 
prices = environment.get_price_data()
pvPower=pv.timeseries.loc[start:end] #type: ignore
#environment.get_pv_data(file="C:\Users\aijaz\vpplib\input\pv")
baseload = pd.read_csv("./input/baseload/df_S_15min.csv")
baseload.drop(columns=["Time"], inplace=True)
baseload.set_index(environment.pv_data.index, inplace=True)

# combine baseload and pv timeseries to get residual load
house_loadshape = pd.DataFrame(baseload["0"].loc[start:end] / 1000)
house_loadshape["pv_gen"] = pv.timeseries.loc[start:end]
house_loadshape["Excess_Power"] = ( pv.timeseries.PVbus_pv-(baseload["0"].loc[start:end] / 1000) )#type :ignore
ExcessPower=house_loadshape.Excess_Power
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

prices_use=prices.iloc[40:num_hours+40, 0].values
pvPower_use=ExcessPower # type: ignore
systemLoad=-1*pvPower_use
systemLoad[systemLoad<0]=0
outputLoad=1*systemLoad
outputLoad[outputLoad>maxDischargingPower]=maxDischargingPower
pvPower_use[pvPower_use<0]=0
# Create models
m = gp.Model('MIP')
m.setParam('TimeLimit',5*60)

pricesModel = {t: prices_use[(t *time_step_size)//60] for t in set_T}
pvPowerModel= {t: pvPower_use[(t *time_step_size)//60] for t in set_T}
loadModel= {t: outputLoad[(t *time_step_size)//60] for t in set_T}
systemLoadModel={t: systemLoad[(t *time_step_size)//60] for t in set_T}
chargingPower = {t:m.addVar(vtype=GRB.CONTINUOUS,lb=0,ub=maxChargingPower,name="chargingPower_{}".format(t)) for t in set_T}
dischargingPower = {t:m.addVar(vtype=GRB.CONTINUOUS,lb=0,ub=maxDischargingPower,name="dischargingPower_{}".format(t)) for t in set_T}
chargingState = {t:m.addVar(vtype=GRB.INTEGER,lb=0,ub=1,name="chargingState_{}".format(t)) for t in set_T}
dischargingState = {t:m.addVar(vtype=GRB.INTEGER ,lb=0,ub=1,name="dischargingState_{}".format(t)) for t in set_T}
SoC={t:m.addVar(vtype=GRB.CONTINUOUS,lb=minimumSoC,ub=maximumSoC ,name="chargePercentage_{}".format(t)) for t in set_T}

##Constraints on charging process
#chargingPower constraints
constraints_eq1={t: m.addConstr(lhs = chargingPower[t],sense = GRB.LESS_EQUAL,rhs= chargingState[t] * maxChargingPower ,name='chargingPower_constraint_{}'.format(t)) for t in set_T} # type: ignore 
#state of charge constraint
constraints_eq2={t: m.addConstr(lhs = SoC[t-1] + chargingEfficiency*timestep*chargingPower[t],sense = GRB.LESS_EQUAL,rhs= maximumSoC,name='chargingState_constraint_{}'.format(t)) for t in range(1,T-1)} # type: ignore
constraints_eq7={t: m.addConstr(lhs = chargingPower[t],sense = GRB.LESS_EQUAL,rhs= pvPowerModel[t] ,name='chargingPowerPV_constraint_{}'.format(t)) for t in set_T} # type: ignore
# Constraints on discharging process
#chargingPower constraints
constraints_eq3={t: m.addConstr(lhs = dischargingPower[t],sense = GRB.LESS_EQUAL,rhs= dischargingState[t] * maxDischargingPower ,name='dischargingPower_constraint_{}'.format(t)) for t in set_T} # type: ignore
constraints_eq8={t: m.addConstr(lhs = dischargingPower[t],sense = GRB.GREATER_EQUAL,rhs= dischargingState[t] *loadModel[t] ,name='dischargingPowerPV_constraint_{}'.format(t)) for t in set_T} # type: ignore
#state of charge constraint
constraints_eq4={t: m.addConstr(lhs = SoC[t-1] - (1/dischargingEfficiency)*timestep*dischargingPower[t],sense = GRB.GREATER_EQUAL,rhs= minimumSoC ,name='dischargingState_constraint_{}'.format(t)) for t in range(1,T-1)} # type: ignore

#Constraints on Processes
constraints_eq5={t: m.addConstr(lhs = chargingState[t]+dischargingState[t],sense = GRB.LESS_EQUAL,rhs= 1 ,name='chargingDischargingCorrelation_constraint_{}'.format(t)) for t in set_T} # type: ignore

#Constraints on Charge
constraints_eq6=   {t: m.addConstr(lhs=SoC[t] ,sense = GRB.EQUAL,rhs= SoC[t-1]+chargingEfficiency*timestep*chargingPower[t]-timestep*(1/dischargingEfficiency)*dischargingPower[t],name='charge_constraint_{}'.format(t)) for t in range(1,T-1)} # type: ignore
constraints_eq6[0]=    m.addConstr(lhs=SoC[0] ,sense = GRB.EQUAL,rhs= startSoC,name='charge_constraint_{}'.format(0)) # type: ignore

objective = gp.quicksum(-1 * chargingPower[t] * timestep * prices.iloc[t, 0] + (dischargingPower[t] - dischargingState[t] *loadModel[t])* timestep * prices.iloc[t, 0] + (pvPowerModel[t] )* timestep * prices.iloc[t, 0]for t in set_T) # type: ignore

m.ModelSense = GRB.MAXIMIZE
m.setObjective(objective)
 # Solve the optimization problem
m.optimize()

# Extracting timeseries
charging_power_values = [chargingPower[t].X for t in set_T]
discharging_power_values = [dischargingPower[t].X for t in set_T]
systemLoad_values=[ systemLoadModel[t] for t in set_T]
SoC_values = [SoC[t].X for t in range(1, T-1)]  # Starting from 1 because we don't have charge[0]
SoC_values.insert(0,startSoC)
time_steps = list(set_T)



plt.figure(figsize=(12, 6))

# Plotting Charging Power
plt.subplot(3, 1, 1)
plt.plot(time_steps,charging_power_values, label='charging Power',drawstyle='steps')
plt.ylabel('Power (kW)')
plt.title('charging Power over Time')
plt.legend()

# Plotting Discharging Power
plt.subplot(3, 1, 2)
plt.plot(time_steps, discharging_power_values, label='Discharging Power',drawstyle='steps')
plt.ylabel('Power (kW)')
plt.title('Discharging Power over Time')
plt.legend()

# Plotting Charge Percentage
plt.subplot(3, 1, 3)
plt.plot(time_steps, SoC_values, label='Charge ')
plt.xlabel('Time Step')
plt.ylabel('Charge ')
plt.title('Battery Charge over Time')
plt.legend()

plt.tight_layout()

#print(pvPowerModel)
#print(systemLoad_values)
plt.show()
# ESS.residual_load=house_loadshape.residual_load
# ESS.prepare_time_series()
# print("prepare_time_series:")
# print(ESS.timeseries.head())
# ESS.timeseries.plot(figsize=(16, 9))
# plt.show()
