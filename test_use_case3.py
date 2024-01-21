import pandas as pd
import numpy as np
import gurobipy as gp
from gurobipy import GRB
import matplotlib.pyplot as plt
from vpplib.environment import Environment
from vpplib.user_profile import UserProfile
from vpplib.photovoltaic import Photovoltaic

# Parameters for CHP 

C_operating=13 #CHP operating cost [Euro=kwh]
C_startup=10 # CHP startup cost [Euro=kwh]
eta_total = 0.8  # Total efficiency of the CHP
delta_t = 15 #Time-step
chp_Pel_max=4 #Max electric power of CHP
chp_Pel_min=1 #The minimum operating condition of the CHP unit

# Parameters for PV  

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


# Parameters for Battery unit 

cp_bess=5 #BESS nominal capacity (kWh)
charge_efficiency=0.9 #Charge efficiency of BESS 
discharge_efficiency=0.9 #discharge efficiency of BESS
#max_power=1000 #kWh
max_ChargingPower=50
max_DischargingPower=40
max_SOC_bess=1 #Maximum State of Charge
min_SOC_bess=0.3 #Minimum State of Charge


#Parameter for Thermal storage unit (Heat tank)
max_temperature = 60  # °C
min_temperature = 40  # °C
Env_temperature= 21   # °C
mass_of_storage = 500  # kg
cp = 4.2  #specific heat capacity of storage in kJ/kg/K
thermal_energy_loss_per_day = 0.13


#Parameter for Environment


start = "2015-01-01 12:00:00"
end = "2015-01-14 23:45:00"
year = "2015"
time_freq = "15 min"
timebase = 15


#Parameter for User Profile

yearly_thermal_energy_demand = 2500  # kWh
building_type = "DE_HEF33"
latitude = 50.941357
longitude = 6.958307
t_0 = 40  # °C


# initialisation of environment

environment = Environment(
    timebase=timebase, start=start, end=end, year=year, time_freq=time_freq
)

# initialisation of user Profile

user_profile = UserProfile(
    identifier=None,
    latitude=latitude,
    longitude=longitude,
    building_type=building_type,
    comfort_factor=None,
    t_0=t_0,
)


# initialisation of PV

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
"""
#Define optimisation parameter---Naveen

"""

"""
# Access environmental data using the Environment instance ---Naveen

 Heat demand 

 Residual load 
"""

"""
#create variables   ---Naveen

Heat demand 
Residual load 

"""
"""

# Defining decision variables  Naveen/Aijaz

"""

"""
# Defined  constraints 10 #  Naveen/Aijaz
"""
"""
# Defined 7 remaining constraints  Desmond

"""

"""
# Defined objective function ---Desmond

"""