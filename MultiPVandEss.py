#from torch import t
from vpplib.user_profile import UserProfile
from vpplib.environment import Environment
from vpplib.photovoltaic import Photovoltaic
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
identifier = "Cologne"
building_type = "DE_HEF33"
t_0 = 40


# initialisation of enviroment 
environment = Environment(
    timebase=timebase, start=start, end=end, year=year, time_freq=time_freq
)

#initialisation of user profile 
user_profile = UserProfile(
    identifier=identifier,
    latitude=latitude,
    longitude=longitude,
    building_type=building_type,
    comfort_factor=None,
    t_0=t_0,
)
pv = Photovoltaic(
    unit="kW",
    identifier= identifier,
    environment=environment,
    user_profile=user_profile,
    module_lib="SandiaMod",
    module="Canadian_Solar_CS5P_220M___2009_",
    inverter_lib="cecinverter",
    inverter="ABB__MICRO_0_25_I_OUTD_US_208__208V_",
    surface_tilt=20,
    surface_azimuth=200,
    modules_per_string=2,
    strings_per_inverter=2,
    temp_lib='sapm',
    temp_model='open_rack_glass_glass'
)

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






# Getting Prices 
prices = environment.get_price_data()
pv_data=environment.get_pv_data()


# defining variables
timestep=15
T=num_time_step
set_T = range(0,T-1)

prices_use=prices.iloc[0:num_hours, 0].values

# Create models
m = gp.Model('MIP')


pricesModel = {t: prices_use[(t *time_step_size)//60] for t in set_T}

chargingPower = {t:m.addVar(vtype=GRB.CONTINUOUS, name="chargingPower_{}".format(t)) for t in set_T}
dischargingPower = {t:m.addVar(vtype=GRB.CONTINUOUS, name="dischargingPower_{}".format(t)) for t in set_T}
chargingstate = {t: m.addVar(vtype=GRB.BINARY, name=f"chargingstate_{t}") for t in set_T}
charge={t:m.addVar(vtype=GRB.CONTINUOUS ,name="chargePercentage_{}".format(t)) for t in set_T}
dischargingstate = {t: m.addVar(vtype=GRB.BINARY, name=f"dischargingstate_{t}") for t in set_T}


# Constraints of discharging process

#Power constraints
constraints_Power = {t: m.addConstr(
    lhs =dischargingPower[t],
    sense = GRB.LESS_EQUAL,
    rhs=maxDischargingPower*dischargingstate[t],
    name='Power_constraint_{}'.format(t)
    ) for t in range(0,T-1)}

#State of charge constraints 

constraints_stateCharge = {t: m.addConstr(
    lhs = charge[t-1]-(1/dischargingEfficiency)*(timestep/60)*dischargingPower,
    sense = GRB.GREATER_EQUAL,
    rhs=minimumCharge,
    name='statecharge_{}'.format(t)
) for t in range(1,T-1)}

#Constraints on charging process 

#Power constraints
constraints_Power1 = {t: m.addConstr(
    lhs =chargingPower[t],
    sense = GRB.LESS_EQUAL,
    rhs=maxChargingPower*chargingstate[t],
    name='Power_constraint1_{}'.format(t)
    ) for t in range(0,T-1)}

#State of charge constraints 

constraints_stateCharge1 = {t: m.addConstr(
    lhs = charge[t-1]-chargingEfficiency*(timestep/60)*chargingPower,
    sense = GRB.GREATER_EQUAL,
    rhs=maximumCharge,
    name='statecharge1_{}'.format(t)
) for t in range(1,T-1)}

#Wind-PV power constraint
