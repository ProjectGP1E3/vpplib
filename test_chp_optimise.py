import pandas as pd
import numpy as np
import gurobipy as gp
from gurobipy import GRB
import matplotlib.pyplot as plt
from vpplib.environment import Environment
from vpplib.user_profile import UserProfile


# Parameters to be defined
C_fuel = 12.5  # Fuel cost [Euro=kwh]
C_startup = 10  # Costs caused by increased machine wear during switching operations [Euro=kwh]
C_shortdown=1000
P_max = 4  # Maximum electrical power [kw]
eta_total = 0.8  # Total efficiency of the CHP
delta_t = 15 #10*60  # Time step  
t_total = 31*24  # Total time in hrs 
# Define the target temperature
target_temperature = 50  # Set your target temperature here
max_ramp_up = 0.5  # Example maximum ramp-up rate in kW per time step
max_ramp_down = 0.7  # Example maximum ramp-down rate in kW per time step
thermal_energy_loss_per_day = 0.13
comfort_fact=0.01
hysteresis=5

T_on=5
T_off=2

efficiency_per_timestep = 1 - (
            thermal_energy_loss_per_day
            / (24 * (60 /15)))

T = int(t_total*60//delta_t)  # Time horizon  
c=0.3 # need to be calculated 
k=1.2 #need to be calculated 
f_1=0.96 #need to be calculated 
f_2=0.24 #need to be calculated 
g=0.001
eta_charge = 0.9 
cp = 4.2
mass_of_storage = 500

# Values for environment
start = "2015-01-01 12:00:00"
end = "2015-01-14 23:45:00"
year = "2015"
time_freq = "15 min"
timebase = 15

# create an instant of enviroment and initialise
environment = Environment(
    timebase=timebase, start=start, end=end, year=year, time_freq=time_freq
)

# Values for user_profile
yearly_thermal_energy_demand = 2500  # kWh
building_type = "DE_HEF33"
t_0 = 40  # °C

#cerate an instance of user profile and initialise
user_profile = UserProfile(
    identifier=None,
    latitude=None,
    longitude=None,
    thermal_energy_demand_yearly=yearly_thermal_energy_demand,
    building_type=building_type,
    comfort_factor=None,
    t_0=t_0,
)


# Access environmental data using the Environment instance
prices = environment.get_price_data()  #check the shape to be sure 

thermal_demand=user_profile.get_thermal_energy_demand_hourly()  #check the shape 

#take 100hrs of the Data 
thermal_demand_use = thermal_demand.iloc[0:t_total, 0].values  #check  shape
prices_use=prices.iloc[0:t_total,0].values     #check shape 

#set step size 
set_T = range(0,T-1)

#create variables 
P = {t: prices_use[(t *delta_t//60)] for t in set_T}
Q_demand={t:thermal_demand_use[(t *delta_t//60)] for t in set_T}


#initialisation of optimisation process 

# Create models
m = gp.Model('MIP')

max_T_on_off = max(T_on, T_off)
# Defining decision variables
P_available = {t:m.addVar(vtype=GRB.CONTINUOUS, name="P_available_{}".format(t)) for t in set_T} #Actual available electrical output power of the CHP [kW]

P_fuel={t:m.addVar(vtype=GRB.CONTINUOUS, name="P_fuel_{}".format(t)) for t in set_T} # fuel consumption of the CHP[KW]

P_thermal={t:m.addVar(vtype=GRB.CONTINUOUS, name="P_thermal{}".format(t)) for t in set_T} #Thermal output power of the CHP [kW]

sigma_t = {t: m.addVar(vtype=GRB.BINARY, name="sigma_{}".format(t)) for t in set_T}

E_t={t:m.addVar(vtype=GRB.CONTINUOUS, name="E_{}".format(t)) for t in set_T}# state of charge[KWh]

T_current={t:m.addVar(vtype=GRB.CONTINUOUS, name="Current_Temperature_{}".format(t)) for t in set_T}# current temperature in °C

sigma_startup= {t:m.addVar(vtype=GRB.BINARY, name="sigma_startup_{}".format(t)) for t in set_T} #  Start-up process in t

sigma_shortdown= {t:m.addVar(vtype=GRB.BINARY, name="sigma_shortdown_{}".format(t)) for t in set_T} #  Start-up process in t



constraints_operating_state = {t: m.addConstr(
    lhs = P_available[t],
    sense = GRB.EQUAL,
    rhs= sigma_t[t]*P_max,
    name='operating_state_{}'.format(t)
) for t in range(0,T-1)}


constraints_power_dependency = {t: m.addConstr(
    lhs = P_fuel[t],
    sense = GRB.EQUAL,
    rhs= c*sigma_t[t] + k*P_available[t],
    name='Power_dependency_{}'.format(t)
) for t in range(0,T-1)}

constraints_Cogeneration = {t: m.addConstr(
    lhs = P_thermal[t],
    sense = GRB.EQUAL,
    rhs= f_1*P_available[t] + f_2*sigma_t[t],
    name='Cogeneration_{}'.format(t)
) for t in range(0,T-1)}


constraints_thermal_balance = {t: m.addConstr(
    lhs =E_t[t+1],
    sense = GRB.EQUAL,
    rhs=E_t[t] - efficiency_per_timestep*(delta_t/60)*(Q_demand[t]-P_thermal[t]),
    name='thermal_balance_{}'.format(t)
) for t in range(0,T-2)}

constraints_current_temperature = {t: m.addConstr(
    lhs =mass_of_storage*cp*(T_current[t] +273.15),
    sense = GRB.EQUAL,
    rhs=E_t[t],
    name='thermal_balance2_{}'.format(t)
) for t in range(0,T-1)}

# >= contraints

constraints_startup_eq = {t: m.addConstr(
    lhs = sigma_startup[t],
    sense = GRB.GREATER_EQUAL,
    rhs=sigma_t[t]-sigma_t[t-1],
    name='start_up_{}'.format(t)
) for t in range(1,T-1)}

constraints_shortdown_eq = {t: m.addConstr(
    lhs = sigma_shortdown[t],
    sense = GRB.GREATER_EQUAL,
    rhs=sigma_t[t-1]-sigma_t[t],
    name='short_down_{}'.format(t)
) for t in range(1,T-1)}


# <= contraints
constraints_rampup_eq = {t: m.addConstr(
    lhs =P_available[t-1]-P_available[t],
    sense = GRB.LESS_EQUAL,
    rhs=4,
    name='max_constraint_{}'.format(t)
    ) for t in range(1,T-1)}


# <= contraints
constraints_rampdown_eq = {t: m.addConstr(
    lhs =P_available[t]-P_available[t-1],
    sense = GRB.LESS_EQUAL,
    rhs=4,
    name='max_constraint_{}'.format(t)
    ) for t in range(1,T-1)}
#11: charge/discharge are limited by zero and the maximum  capacity

# Objective
objective=gp.quicksum(-P_available[t] * P[t]  +sigma_startup[t] * C_startup +sigma_shortdown[t] * C_shortdown + P_fuel[t] * C_fuel  for t in set_T)
m.ModelSense = GRB.MINIMIZE
m.setObjective(objective)
m.optimize()

P_actual=[]
for t,varname in enumerate(P_fuel.values()):
    P_actual.append(m.getVarByName(varname.VarName).x)


power=0
for t,varname in enumerate(P_available.values()):
    power+=m.getVarByName(varname.VarName).x*delta_t/60
 
print(power)

# Assuming set_T represents the time indices associated with Q_demand
# Plotting Q_demand against time steps
plt.figure(figsize=(8, 6))
plt.plot(P_actual[:3000])  # Plotting the first 1000 time steps
plt.xlabel('Time Steps')
plt.ylabel('Q_demand')
plt.title('Thermal Demand (Q_demand) over Time (First 1000 steps)')
plt.grid(True)
plt.show()