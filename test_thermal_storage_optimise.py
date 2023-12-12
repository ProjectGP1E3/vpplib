from vpplib.user_profile import UserProfile
from vpplib.environment import Environment
from vpplib.heat_pump import HeatPump
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import gurobipy as gp
from gurobipy import GRB


#values for building heat control
num_hours=31*24
time_step_size=15
min_temperature=19.5
max_temperature=22.5
building_capacity=2.07*3.6e6
Thermal_resistance=5.29e-3
window_surface=7.89
comfort_penalty=10
num_time_step=int(num_hours*60//time_step_size) 


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
sun_powers =environment.get_sunPower_data()
prices = environment.get_price_data()

#take 100hrs of the Data 
mean_temp_hours_use = mean_temp_hours.iloc[0:num_hours, 0].values
sun_powers_use=sun_powers.iloc[0:num_hours, 0].values
prices_use=prices.iloc[0:num_hours, 0].values

T=num_time_step
set_T = range(0,T-1)

# Create models
m = gp.Model('MIP')

#create variables 
#Define decision variable: 
T_a = {t: mean_temp_hours_use[(t *time_step_size)//60] for t in set_T}

Phi_s = {t: sun_powers_use[(t *time_step_size)//60] for t in set_T}

P = {t: prices_use[(t *time_step_size)//60] for t in set_T}  #check len 2975

# Defining decision variables
x_vars = {t:m.addVar(vtype=GRB.CONTINUOUS,lb=0, ub=1, name="x_{}".format(t)) for t in set_T}#

T_i = {t:m.addVar(vtype=GRB.CONTINUOUS, name="T_{}".format(t)) for t in range(0,T)} #, lb = T_MIN, ub= T_MAX

nu = {t:m.addVar(vtype=GRB.CONTINUOUS, name="nu_{}".format(t)) for t in range(0,T)}

 #Defining the constraints

      # <= contraints

constraints_less_eq1 = {t: m.addConstr(
    lhs = min_temperature,
    sense = GRB.LESS_EQUAL,
    rhs=T_i[t] + nu[t],
    name='max_constraint_{}'.format(t)
    ) for t in range(0,T)}

# >= contraints

constraints_greater_eq2 = {t: m.addConstr(
    lhs =max_temperature,
    sense = GRB.GREATER_EQUAL,
    rhs=T_i[t] - nu[t],
    name='min_constraint_{}'.format(t)
     ) for t in range(0,T)}


constraints_eq3 = {t: m.addConstr(
    lhs = T_i[t],
    sense = GRB.EQUAL,
    rhs= T_i[t-1] + time_step_size*(1 / (Thermal_resistance * building_capacity) * (T_a[t-1] - T_i[t-1]) + \
                x_vars[t-1] *heat_pump_power(el_power,T_a[t-1])/building_capacity + window_surface*Phi_s[t-1]/building_capacity),
        name='equality_constraint_{}'.format(t)
        ) for t in range(1,T)}

constraints_eq3[0] = m.addConstr(
    lhs = T_i[0],
    sense = GRB.EQUAL,
    rhs= 21,
    name='equality_constraint_{}'.format(0)
    )

 # Objective

objective = gp.quicksum(x_vars[t]*P[t]*el_power/1e6*time_step_size/60 + comfort_penalty*nu[t] for t in set_T)
m.ModelSense = GRB.MINIMIZE
m.setObjective(objective)
 # Solve the optimization problem
m.optimize()


P_actual=[]
for t,varname in enumerate(x_vars.values()):
    P_actual.append(m.getVarByName(varname.VarName).x)

# Assuming set_T represents the time indices associated with Q_demand
# Plotting Q_demand against time steps
plt.figure(figsize=(8, 6))
plt.plot(P_actual[:3000])  # Plotting the first 1000 time steps
plt.xlabel('Time Steps')
plt.ylabel('Q_demand')
plt.title('Thermal Demand (Q_demand) over Time (First 1000 steps)')
plt.grid(True)
plt.show()