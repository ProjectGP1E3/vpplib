import pandas as pd
import numpy as np
import gurobipy as gp
from gurobipy import GRB
import matplotlib.pyplot as plt
from vpplib.environment import Environment
from vpplib.user_profile import UserProfile

PV = pd.read_csv('')
# Values for pv
pv_file = "./input/pv/dwd_pv_data_2015.csv"
module_lib = "SandiaMod"
module = "Canadian_Solar_CS5P_220M___2009_"
inverter_lib = "cecinverter"
inverter = "Connect_Renewable_Energy__CE_4000__240V_"
surface_tilt = 20
surface_azimuth = 200
modules_per_string = 10
strings_per_inverter = 2
temp_lib = 'sapm'
temp_model = 'open_rack_glass_glass'


prices = pd.read_csv('')
baseload = pd.read_csv('')


# Values for el storage
charge_efficiency = 0.98
discharge_efficiency = 0.98
max_power = 4  # kW
capacity = 4  # kWh
max_c = 1  # factor between 0.5 and 1.2



environment = Environment(
    timebase=timebase,
    timezone="Europe/Berlin",
    start=start,
    end=end,
    year=year,
    time_freq=time_freq,
)

environment.get_pv_data(file=pv_file)


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

