import pandas as pd
import numpy as np
import random
import gurobipy as gp
from gurobipy import GRB
import pickle as pkl
import matplotlib.pyplot as plt
from vpplib.environment import Environment
from vpplib.user_profile import UserProfile



# Parameters to be defined
C_startup = 2  # Costs caused by increased machine wear during switching operations [Euro=kwh]
C_fuel = 12.5  # Fuel cost [Euro=kwh]
P_max = 4  # Maximum electrical power [kw]
P_min = 1.5  # Minimum electric power [kw]
eta_total = 0.8  # Total efficiency of the CHP
E_max = 708  # Maximum state of charge for the thermal storage [kwh]
Q_lose1 = 0.005  # Thermal losses of the thermal storage between two periods when idle  [kwh]
q_lose = 0.005  # Percentage state of charge that will be lost between two periods
Q_dot_max = 6  # Maximum charging rate of the thermal storage [kw]
Q_dot_min = 0  # Minimum charging rate of the thermal storage  [kw]
eta_charge = 0.9  # Efficiency of charging the thermal storage
eta_discharge = 0.85  # Efficiency during discharging from the thermal storage
delta_t = 10*60  # Time step  
t_total = 31*24  # Total time in hrs 
T = int(t_total*3600//delta_t)  # Time horizon  
max_ramp_up = 0.5  # Example maximum ramp-up rate in kW per time step
max_ramp_down = 0.7  # Example maximum ramp-down rate in kW per time step
c=0.3 # need to be calculated 
k=1.2 #need to be calculated 
f_1=0.96 #need to be calculated 
f_2=0.24 #need to be calculated 



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

#cerate an instance of user profile and ninitialise
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


last_ramp_up=thermal_demand_use.index[0]
print(last_ramp_up)

#set step size 
set_T = range(0,T-1)

#create variables 
P = {t: prices_use[(t *delta_t//3600)] for t in set_T}
Q_demand={t:thermal_demand_use[(t *delta_t//3600)] for t in set_T}


#initialisation of optimisation process 

# Create models
m = gp.Model('MIP')

# Defining decision variables
P_available = {t:m.addVar(vtype=GRB.CONTINUOUS, name="P_available_{}".format(t)) for t in set_T} #Actual available electrical output power of the CHP [kW]

sigma_startup= {t:m.addVar(vtype=GRB.BINARY, name="sigma_startup_{}".format(t)) for t in set_T} #  Start-up process in t

P_fuel={t:m.addVar(vtype=GRB.CONTINUOUS, name="P_fuel_{}".format(t)) for t in set_T} # fuel consumption of the CHP[KW]

E_t={t:m.addVar(vtype=GRB.CONTINUOUS, name="E_{}".format(t)) for t in set_T}# state of charge[KWh]

P_set_value={t:m.addVar(vtype=GRB.CONTINUOUS, name="P_set_value_{}".format(t)) for t in set_T}  #set value for the electrical output power of the CHP [kW]

sigma_t = {t: m.addVar(vtype=GRB.BINARY, name="sigma_{}".format(t), lb=0 if t != 0 else 0) for t in set_T}

P_thermal={t:m.addVar(vtype=GRB.CONTINUOUS, name="P_thermal{}".format(t)) for t in set_T} #Thermal output power of the CHP [kW]

Q_dot_charge={t:m.addVar(vtype=GRB.CONTINUOUS, name="Q_charge_{}".format(t)) for t in set_T} # Charging power [kW]

Q_dot_discharge={t:m.addVar(vtype=GRB.CONTINUOUS, name="Q_discharge_{}".format(t)) for t in set_T} #  Discharging power [kW]


# <= contraints
constraints_less_eq = {t: m.addConstr(
    lhs = P_min*sigma_t[t],
    sense = GRB.LESS_EQUAL,
    rhs= P_set_value[t],
    name='max_constraint_{}'.format(t)
    ) for t in range(0,T-1)}

# >= contraints
constraints_greater_eq = {t: m.addConstr(
    lhs = P_max*sigma_t[t],
    sense = GRB.GREATER_EQUAL,
    rhs=P_set_value[t],
    name='min_constraint_{}'.format(t)
) for t in range(0,T-1)}

# 3: Power-dependent efficiency
 # == contraints
constraints_eq = {t: m.addConstr(
    lhs = P_fuel[t],
    sense = GRB.EQUAL,
    rhs= c*sigma_t[t] + k*P_set_value[t],
    name='equality_constraint_{}'.format(t)
) for t in range(0,T-1)}

#4: Cogeneration
# == contraints
constraints_eq = {t: m.addConstr(
    lhs = P_thermal[t],
    sense = GRB.EQUAL,
    rhs= f_1*P_set_value[t] + f_2*sigma_t[t],
    name='equality_constraint_{}'.format(t)
) for t in range(0,T-1)}

#5: Start-up
# >= contraints
constraints_greater_eq = {t: m.addConstr(
    lhs = sigma_startup[t],
    sense = GRB.GREATER_EQUAL,
    rhs=sigma_t[t]-sigma_t[t-1],
    name='min_constraint_{}'.format(t)
) for t in range(1,T-1)}

#6,7,8 Power gradient constraints
#not included equation 6, 7:  if we need to extend the model could be included
#assumped no zero inertia for CHP g=0
# == contraints
constraints_eq = {t: m.addConstr(
    lhs = P_available[t],
    sense = GRB.EQUAL,
    rhs= P_set_value[t],
    name='equality_constraint_{}'.format(t)
) for t in range(0,T-1)}

#9 thermal balance 
# == contraints

constraints_eq = {t: m.addConstr(
    lhs =-Q_demand[t]+eta_discharge*Q_dot_discharge[t]-Q_dot_charge[t] +P_thermal[t],
    sense = GRB.EQUAL,
    rhs= 0,
    name='equality_constraint_{}'.format(t)
) for t in range(1,T-1)}

constraints_eq = {t: m.addConstr(
    lhs =E_t[t]*q_lose+delta_t*(eta_charge*Q_dot_charge[t]-Q_dot_discharge[t]*eta_discharge)-Q_lose1,
    sense = GRB.EQUAL,
    rhs= E_t[t+1],
    name='equality_constraint_{}'.format(t)
) for t in range(0,T-2)}

#11: thermal storage is limited by zero and the maximum storage capacity

# <= contraints
constraints_less_eq = {t: m.addConstr(
    lhs = 0,
    sense = GRB.LESS_EQUAL,
    rhs= E_t[t],
    name='max_constraint_{}'.format(t)
    ) for t in range(0,T-1)}

# >= contraints
constraints_greater_eq = {t: m.addConstr(
    lhs = E_max,
    sense = GRB.GREATER_EQUAL,
    rhs=E_t[t],
    name='min_constraint_{}'.format(t)
) for t in range(0,T-1)}

#11: charge/discharge are limited by zero and the maximum  capacity


constraints_eq[0] = m.addConstr(
    lhs = sigma_t[0],
    sense = GRB.EQUAL,
    rhs= 0,
    name='equality_constraint_{}'.format(0)
    )



# Objective
objective=gp.quicksum(-P_available[t] * P[t] +sigma_startup[t] * C_startup +P_fuel[t] * C_fuel for t in set_T)
m.ModelSense = GRB.MINIMIZE
m.setObjective(objective)
m.optimize()

P_actual=[]
for t,varname in enumerate(P_available.values()):
    P_actual.append(m.getVarByName(varname.VarName).x)



# Assuming set_T represents the time indices associated with Q_demand
# Plotting Q_demand against time steps
plt.figure(figsize=(8, 6))
plt.plot(P_actual[:1000])  # Plotting the first 1000 time steps
plt.xlabel('Time Steps')
plt.ylabel('Q_demand')
plt.title('Thermal Demand (Q_demand) over Time (First 1000 steps)')
plt.grid(True)
plt.show()