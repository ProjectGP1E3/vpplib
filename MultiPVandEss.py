from torch import t
from vpplib.user_profile import UserProfile
from vpplib.environment import Environment
from vpplib.heat_pump import HeatPump
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import gurobipy as gp
from gurobipy import GRB


# Values for environment
start = "2015-01-01 12:00:00"
end = "2015-01-31 23:45:00"
year = "2015"
time_freq = "15 min"
timestamp_int = 48
timestamp_str = "2015-01-01 12:00:00"
timebase = 15

#values for time interval
num_hours=31*24
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

# Battery Variables Initialization
maxChargingPower=50
maxDischargingPower=40
dischargingEfficiency=0.98
chargingEfficiency=0.98
minimumCharge=0
maximumCharge=4
max_power = 4  # kW
capacity = 4  # kWh
max_c = 1
timebase = 15

# initialisation of enviroment 
environment = Environment(
    timebase=timebase, start=start, end=end, year=year, time_freq=time_freq
)

#initialisation of user profile 
user_profile = UserProfile(
    identifier=name,
    latitude=latitude,
    longitude=longitude,
    building_type=building_type,
    comfort_factor=None,
    t_0=t_0,
)

# Getting Prices 
prices = environment.get_price_data()
environment.get_pv_data(file="D:/Project/vpplib/input/pv/dwd_pv_data_2015.csv")


# defining variables
timestep=15
T=num_time_step
set_T = range(0,T-1)

prices_use=prices.iloc[0:num_hours, 0].values

# Create models
m = gp.Model('MIP')


pricesModel = {t: prices_use[(t *time_step_size)//60] for t in set_T}

chargingPower = {t:m.addVar(vtype=GRB.CONTINUOUS,lb=0,ub=maxChargingPower,name="chargingPower_{}".format(t)) for t in set_T}
dischargingPower = {t:m.addVar(vtype=GRB.CONTINUOUS,lb=0,ub=maxDischargingPower,name="dischargingPower_{}".format(t)) for t in set_T}
chargingState = {t:m.addVar(vtype=GRB.INTEGER,lb=0,ub=1,name="chargingState_{}".format(t)) for t in set_T}
dischargingState = {t:m.addVar(vtype=GRB.INTEGER ,lb=0,ub=1,name="dischargingState_{}".format(t)) for t in set_T}
charge={t:m.addVar(vtype=GRB.CONTINUOUS,lb=minimumCharge,ub=maximumCharge ,name="chargePercentage_{}".format(t)) for t in set_T}

#Constraints on charging process
#chargingPower constraints
constraints_eq1={t: m.addConstr(lhs = chargingPower[t],sense = GRB.LESS_EQUAL,rhs= chargingState[t] * maxChargingPower ,name='chargingPower_constraint_{}'.format(t)) for t in range(0,T)} # type: ignore 
#state of charge constraint
constraints_eq2={t: m.addConstr(lhs = charge[t-1] + chargingEfficiency*timestep*chargingPower[t],sense = GRB.LESS_EQUAL,rhs= maximumCharge,name='chargingState_constraint_{}'.format(t)) for t in range(0,T)} # type: ignore

#Constraints on discharging process
#chargingPower constraints
constraints_eq3={t: m.addConstr(lhs = dischargingPower[t],sense = GRB.LESS_EQUAL,rhs= dischargingState[t] * maxDischargingPower ,name='dischargingPower_constraint_{}'.format(t)) for t in range(0,T)} # type: ignore
#state of charge constraint
constraints_eq4={t: m.addConstr(lhs = charge[t-1] - 1/dischargingEfficiency*timestep*dischargingPower[t],sense = GRB.LESS_EQUAL,rhs= minimumCharge ,name='dischargingState_constraint_{}'.format(t)) for t in range(0,T)} # type: ignore

#Constraints on Processes
constraints_eq5={t: m.addConstr(lhs = chargingState[t]+dischargingState[t],sense = GRB.LESS_EQUAL,rhs= 1 ,name='chargingDischargingCorrelation_constraint_{}'.format(t)) for t in range(0,T)} # type: ignore

objective = gp.quicksum(-1*chargingPower[t]*timestep*prices[t] + dischargingPower[t]*timestep*prices[t] for t in set_T)  # type: ignore
m.ModelSense = GRB.MINIMIZE
m.setObjective(objective)
 # Solve the optimization problem
m.optimize()