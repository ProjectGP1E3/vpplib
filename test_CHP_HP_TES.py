import pandas as pd
import numpy as np
import gurobipy as gp
from gurobipy import GRB
import matplotlib.pyplot as plt
from vpplib.environment import Environment
from vpplib.user_profile import UserProfile



# Parameters to be defined for CHP unit 
C_fuel = 12.5  # Fuel cost [Euro=kwh]
C_startup = 10  # Costs caused by increased machine wear during switching on operations [Euro=kwh]
C_shortdown=10  # Costs caused by increased machine wear during  switching off operations [Euro=kwh]
T_on=1  # minimum runtime of CHP
T_off=2 # minimum off time of CHP
P_nom=5   #nominal electrical power in kw 
eta_total = 0.8  # Total efficiency of the CHP
c=0.3 # calculated according Steck PHD thesis see (Steck 2012 page 34)
k=1.2 # calculated according Steck PHD thesis see (Steck 2012 page 34) 
f_1=0.96 # calculated according Steck PHD thesis see (Steck 2012 page 35) 
f_2=0.24 # calculated according Steck PHD thesis see (Steck 2012 page 35)


#Parameter to be defined for Thermal storage unit 
maximum_temperature = 60  # maximum temperature of TES in °C
min_temperature=40     # minimum temperature of TES in °C
mass_of_storage = 500  # kg  
cp = 4.2      #specific heat capacity of storage in kJ/kg/K
k_sto= 1.12   #  thermal conductivity of storage material W/m^2K
A_sto=3.39    #  Area of storage unit in m^2

#Parameter to be defined for Heat pump 
heat_pump_type = "Air"
heat_sys_temp = 60
el_power = 5  # nominal electrical power in kw 

def heat_pump_power(phi_e, tmp):
    """Takes an electrical power flow and converts it to a heat flow.

    :param phi_e: The electrical power
    :type phi_e: Float
    :return: Returns the heat flow as an integer
    """
    cop=(
                6.81
                - 0.121 * (heat_sys_temp - tmp)
                + 0.00063 * (heat_sys_temp - tmp) ** 2
            )
    
    return phi_e*cop

#Parameter to be defined for Enviroment
start = "2015-01-01 12:00:00"
end = "2015-01-14 23:45:00"
year = "2015"
timebase = 15
time_freq = "15 min"

#Parameter to be defined for user Profile
yearly_thermal_energy_demand = 12500
building_type = "DE_HEF33"
t_0 = 40    # °C

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


#Define optimisation parameter
time_step_size = 15 #10*60  # Time step in minute  
num_hours = 10*24  # Total time in hrs 
comfort_fact=10     #comfort factor 
num_time_step=int(num_hours*60//time_step_size) 
T=num_time_step
set_T = range(0,T)

# Create models
m = gp.Model('MIP')

# Access environmental data using the Environment instance

prices = environment.get_price_data()  #check the shape to be sure 

thermal_demand=user_profile.get_thermal_energy_demand_hourly()  #check the shape 

mean_temp_hours = environment.get_mean_temp_hours()   #check the shape 

print(prices.shape)