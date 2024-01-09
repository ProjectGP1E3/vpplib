from vpplib.user_profile import UserProfile
from vpplib.environment import Environment
from vpplib.heat_pump import HeatPump
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import gurobipy as gp
from gurobipy import GRB


#time horizone
num_hours=31*24
time_step_size=15
num_time_step=int(num_hours*60//time_step_size) 
comfort_penalty=10


# Values for environment
start = "2015-01-01 12:00:00"
end = "2015-01-14 23:45:00"
year = "2015"
time_freq = "15 min"
timestamp_int = 48
timestamp_str = "2015-01-01 12:00:00"
timebase = 15


# Values for user_profile
yearly_thermal_energy_demand = 12500
building_type = "DE_HEF33"
t_0 = 40

# Values for Heatpump
el_power = 5000  # 5kW electric
th_power = 8  # kW thermal
heat_pump_type = "Air"
heat_sys_temp = 60
ramp_up_time = 1 / 15  # timesteps
ramp_down_time = 1 / 15  # timesteps
min_runtime = 1  # timesteps
min_stop_time = 2  # timesteps


# Values for Thermal Storage
max_temperature = 60  # °C
min_temperature = 40  # °C
Env_temperature= 21   # °C
mass_of_storage = 500  # kg
cp = 4200  #J/kg/k
thermal_energy_loss_per_day = 0.13  #kJ
k_sto= 1.12       #W/m^2k   
A_sto = 3.39      #m^2

# initialisation of enviroment 
environment = Environment(
    timebase=timebase, start=start, end=end, year=year, time_freq=time_freq
)

#initialisation of user profile 
user_profile = UserProfile(
    identifier=None,
    latitude=None,
    longitude=None,
    thermal_energy_demand_yearly=yearly_thermal_energy_demand,
    building_type=building_type,
    comfort_factor=None,
    t_0=t_0,
)

#initialise  heat pump

user_profile.get_thermal_energy_demand()
   
hp = HeatPump(
    identifier="hp1",
    unit="kW",
    environment=environment,
    user_profile=user_profile,
    el_power=el_power,
    th_power=th_power,
    heat_pump_type=heat_pump_type,
    heat_sys_temp=heat_sys_temp,
    ramp_up_time=ramp_up_time,
    ramp_down_time=ramp_down_time,
    min_runtime=min_runtime,
    min_stop_time=min_stop_time,
)


def heat_pump_power(phi_e, tmp):
    """Takes an electrical power flow and converts it to a heat flow.

    :param phi_e: The electrical power
    :type phi_e: Float
    :return: Returns the heat flow as an integer
    """
    cop=hp.get_current_cop(tmp)
    
    return phi_e*cop

# Access environmental data using the Environment instance

mean_temp_hours = environment.get_mean_temp_hours()
prices = environment.get_price_data()
thermal_demand=user_profile.get_thermal_energy_demand_hourly()  #check the shape 

#take 100hrs of the Data 
mean_temp_hours_use = mean_temp_hours.iloc[0:num_hours, 0].values
prices_use=prices.iloc[0:num_hours, 0].values
thermal_demand_use = thermal_demand.iloc[0:num_hours, 0].values  #check  shape

T=num_time_step
set_T = range(0,T)

# Create models
m = gp.Model('MIP')

#create variables 
#Define decision variable: 
T_a = {t: mean_temp_hours_use[(t *time_step_size)//60] for t in set_T}
Q_demand={t:thermal_demand_use[(t *time_step_size//60)] for t in set_T}

P = {t: prices_use[(t *time_step_size)//60] for t in set_T}  #check len 2975

# Defining decision variables
#x_vars = {t:m.addVar(vtype=GRB.CONTINUOUS,lb=0, ub=1, name="x_{}".format(t)) for t in set_T}# heat pump operation mode 

x_vars = {t:m.addVar(vtype=GRB.BINARY, name="x_{}".format(t)) for t in set_T}# heat pump operation mode 

T_sto = {t:m.addVar(vtype=GRB.CONTINUOUS, name="T_{}".format(t)) for t in set_T} #, lb = T_MIN, ub= T_MAX

nu = {t:m.addVar(vtype=GRB.CONTINUOUS, name="nu_{}".format(t)) for t in set_T}

P_HP= {t:m.addVar(vtype=GRB.CONTINUOUS, name="P_HP_{}".format(t)) for t in set_T}  # Electrical consumption of Heat pump

Q_HP= {t:m.addVar(vtype=GRB.CONTINUOUS, name="Q_HP_{}".format(t)) for t in set_T}  # Electrical consumption of Heat pump


 #Defining the constraints


constraints_eq1 = {t: m.addConstr(
    lhs = P_HP[t],
    sense = GRB.EQUAL,
    rhs= x_vars[t]*el_power,
        name='equality_constraint1_{}'.format(t)
        ) for t in set_T}


constraints_eq2 = {t: m.addConstr(
    lhs = Q_HP[t],
    sense = GRB.EQUAL,
    rhs= x_vars[t]*heat_pump_power(el_power,T_a[t]),
        name='equality_constraint2_{}'.format(t)
        ) for t in set_T}

      # <= contraints

constraints_less_eq3 = {t: m.addConstr(
    lhs = min_temperature,
    sense = GRB.LESS_EQUAL,
    rhs=T_sto[t] + nu[t],
    name='max_constraint_{}'.format(t)
    ) for t in set_T}

# >= contraints

constraints_greater_eq4 = {t: m.addConstr(
    lhs =max_temperature,
    sense = GRB.GREATER_EQUAL,
    rhs=T_sto[t],
    name='min_constraint_{}'.format(t)
     ) for t in set_T}


constraints_eq5 = {t: m.addConstr(
    lhs = mass_of_storage*cp*(T_sto[t]-T_sto[t-1]),
    sense = GRB.EQUAL,
    rhs= time_step_size*60*(Q_HP[t]-Q_demand[t]- k_sto*A_sto*(T_sto[t]-Env_temperature)),
        name='equality_constraint3_{}'.format(t)
        ) for t in range(1,T)}


 # Objective

objective = gp.quicksum(P_HP[t]*P[t]*time_step_size/60 + comfort_penalty*nu[t] for t in set_T)
m.ModelSense = GRB.MINIMIZE
m.setObjective(objective)
 # Solve the optimization problem
m.optimize()


P_actual=[]
for t,varname in enumerate(Q_HP.values()):
    P_actual.append(m.getVarByName(varname.VarName).x)

# Assuming set_T represents the time indices associated with Q_demand
# Plotting Q_demand against time steps
plt.figure(figsize=(8, 6))
plt.plot(P_actual[:100])  # Plotting the first 1000 time steps
plt.xlabel('Time Steps')
plt.ylabel('Q_demand')
plt.title('Thermal Demand (Q_demand) over Time (First 1000 steps)')
plt.grid(True)
plt.show()