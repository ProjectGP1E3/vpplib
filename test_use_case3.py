import pandas as pd
import numpy as np
import gurobipy as gp
from gurobipy import GRB
import matplotlib.pyplot as plt
from vpplib.environment import Environment
from vpplib.user_profile import UserProfile
from vpplib.photovoltaic import Photovoltaic
from vpplib.electrical_energy_storage import ElectricalEnergyStorageSimses

# Parameters for CHP 

C_operating=13 #CHP operating cost [Euro=kwh]
comfort_fact=10
C_fuel=0.119  #Euro/kwh
C_shortdown=0.495  #Euro/kwh 
C_startup=0.495 # CHP startup cost [Euro/kwh]
eta_total = 0.8  # Total efficiency of the CHP
delta_t = 15 #Time-step
chp_Pel_max=4 #Max electric power of CHP
chp_Pel_min=1 #The minimum operating condition of the CHP unit
T_on=5  # minimum runtime of CHP
T_off=5 # minimum off time of CHP
P_nom=4   #nominal electrical power in kw 
eta_total = 0.8  # Total efficiency of the CHP
c=0.3 # calculated according Steck PHD thesis see (Steck 2012 page 34)
k=1.2 # calculated according Steck PHD thesis see (Steck 2012 page 34) 
f_1=0.96 # calculated according Steck PHD thesis see (Steck 2012 page 35) 
f_2=0.24 # calculated according Steck PHD thesis see (Steck 2012 page 35)

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
max_ChargingPower=0.4
max_DischargingPower=0.3
max_SOC_bess=4 #Maximum State of Charge
min_SOC_bess=0.3 #Minimum State of Charge


#Parameter for Thermal storage unit (Heat tank)
max_temperature = 60  # °C
min_temperature = 40  # °C
Env_temperature= 21   # °C
mass_of_storage = 500  # kg
cp = 4.2  #specific heat capacity of storage in kJ/kg/K
thermal_energy_loss_per_day = 0.13
min_discharge_rate=0
max_discharge_rate=3


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


#Define optimisation parameter---Naveen
time_step_size = 15 #10*60  # Time step in minute  
num_hours = 10*24  # Total time in hrs 
num_time_step=int(num_hours*60//time_step_size) 
T=num_time_step
set_T = range(0,T)

# Create models
m = gp.Model('MIP')
m.setParam('TimeLimit',3*60)

# Access environmental data using the Environment instance ---Naveen

 #Heat demand 
thermal_demand=user_profile.get_thermal_energy_demand_hourly()  #check the shape 

 #Residual load 
environment.get_pv_data(file="./input/pv/dwd_pv_data_2015.csv")
baseload = pd.read_csv("./input/baseload/df_S_15min.csv")
baseload.drop(columns=["Time"], inplace=True)

#create variables  
#Price

prices = environment.get_price_data()  #check the shape to be sure 

#Heat demand 
thermal_demand_use = thermal_demand.iloc[0:num_hours, 0].values

#Base load 
baseload_use = baseload.iloc[0:num_hours, 0].values/1000

#price
prices_use=prices.iloc[0:num_hours,0].values     #check shape 

# Defining decision variables  Naveen/Aijaz
Q_demand = {t: thermal_demand_use[(t *time_step_size)//60] for t in set_T}

P = {t: prices_use[(t *time_step_size)//60] for t in set_T}  #check len 960 for 10days

baseload_Model= {t: baseload_use[(t *time_step_size)//60] for t in set_T}

P_available = {t:m.addVar(vtype=GRB.CONTINUOUS,name="P_chp_l{}".format(t)) for t in set_T} # total electrical power from chp

chargingState = {t:m.addVar(vtype=GRB.BINARY,name="chargingState_{}".format(t)) for t in set_T} # 0 or 1 based on the charging state

chargingPower = {t:m.addVar(vtype=GRB.CONTINUOUS,lb=0,ub=max_ChargingPower,name="chargingPower_{}".format(t)) for t in set_T}

dischargingState = {t:m.addVar(vtype=GRB.BINARY ,name="dischargingState_{}".format(t)) for t in set_T} # 0 or 1 based on the discharging state

dischargingPower = {t:m.addVar(vtype=GRB.CONTINUOUS,lb=0,ub=max_DischargingPower,name="dischargingPower_{}".format(t)) for t in set_T}

P_thermal={t:m.addVar(vtype=GRB.CONTINUOUS, name="P_thermal{}".format(t)) for t in set_T} #Thermal output power of the CHP [kW]

sigma_t = {t: m.addVar(vtype=GRB.BINARY, name="sigma_{}".format(t)) for t in set_T} # based on CHP operation

E_t={t:m.addVar(vtype=GRB.CONTINUOUS, name="E_{}".format(t)) for t in set_T}# state of charge Thermal Storage[KWh]

T_sto={t:m.addVar(vtype=GRB.CONTINUOUS, name="Current_Temperature_{}".format(t)) for t in set_T}# current temperature in °C

SOC={t:m.addVar(vtype=GRB.CONTINUOUS,lb=min_SOC_bess,ub=max_SOC_bess ,name="chargePercentage_{}".format(t)) for t in set_T}

sigma_startup= {t:m.addVar(vtype=GRB.BINARY, name="sigma_startup_{}".format(t)) for t in set_T} #  Start-up process in t

sigma_shortdown= {t:m.addVar(vtype=GRB.BINARY, name="sigma_shortdown_{}".format(t)) for t in set_T} #  Start-up process in t

Q_dot_charge={t:m.addVar(vtype=GRB.CONTINUOUS, name="Q_dot_charge_{}".format(t)) for t in set_T}# charging rate [KW]

Q_dot_discharge={t:m.addVar(vtype=GRB.CONTINUOUS, name="Q_dot_discharge_{}".format(t)) for t in set_T}# discharging rate [KW]

P_fuel={t:m.addVar(vtype=GRB.CONTINUOUS, name="P_fuel_{}".format(t)) for t in set_T} # fuel consumption of the CHP[KW]

P_chp_l = {t:m.addVar(vtype=GRB.CONTINUOUS,name="P_chp_l{}".format(t)) for t in set_T} # Power from CHP to electric load

nu = {t:m.addVar(vtype=GRB.CONTINUOUS, name="nu_{}".format(t)) for t in set_T} # thermal disutility in °C




# Defined  constraints 10 #  Naveen/Aijaz

#constraints for CHP operation

# Define constraints uptime
constraints_uptime_eq = {t: m.addConstr(
    lhs=sigma_t[t] - sigma_t[t - 1],
    sense=GRB.LESS_EQUAL,
    rhs=sigma_t[t + j],
    name=f"max_constraint_{t}"
) for t in range(1, T - T_on-1) for j in range(1, T_on+1)}

# Define constraints downtime
constraints_downtime_eq = {t: m.addConstr(
    lhs=sigma_t[t-1] - sigma_t[t] +sigma_t[t + j],
    sense=GRB.LESS_EQUAL,
    rhs=1,
    name=f"max_constraint_{t}"
) for t in range(1, T - T_off-1) for j in range(1, T_off+1)}

constraints_operating_state = {t: m.addConstr(
    lhs = P_available[t],
    sense = GRB.EQUAL,
    rhs= sigma_t[t]*P_nom,
    name='operating_state_{}'.format(t)
) for t in range(0,T)}

constraints_power_dependency = {t: m.addConstr(
    lhs = P_fuel[t],
    sense = GRB.EQUAL,
    rhs= c*sigma_t[t] + k*P_available[t],
    name='Power_dependency_{}'.format(t)
) for t in range(0,T)}

constraints_Cogeneration = {t: m.addConstr(
    lhs = P_thermal[t],
    sense = GRB.EQUAL,
    rhs= f_1*P_available[t] + f_2*sigma_t[t],
    name='Cogeneration_{}'.format(t)
) for t in range(0,T)}

constraints_startup_eq = {t: m.addConstr(
    lhs = sigma_startup[t],
    sense = GRB.GREATER_EQUAL,
    rhs=sigma_t[t]-sigma_t[t-1],
    name='start_up_{}'.format(t)
) for t in range(1,T)}


constraints_shortdown_eq = {t: m.addConstr(
    lhs = sigma_shortdown[t],
    sense = GRB.GREATER_EQUAL,
    rhs=sigma_t[t-1]-sigma_t[t],
    name='short_down_{}'.format(t)
) for t in range(1,T)}

# <= contraints
constraints_rampup_eq = {t: m.addConstr(
    lhs =P_available[t-1]-P_available[t],
    sense = GRB.LESS_EQUAL,
    rhs=4,
    name='max_constraint_{}'.format(t)
    ) for t in range(1,T)}

# <= contraints
constraints_rampdown_eq = {t: m.addConstr(
    lhs =P_available[t]-P_available[t-1],
    sense = GRB.LESS_EQUAL,
    rhs=4,
    name='max_constraint_{}'.format(t)
    ) for t in range(1,T)}

#Constraint Equations Thermal storage interface CHP

constraints_thermal_balance1 = {t: m.addConstr(
    lhs =-Q_demand[t] + Q_dot_discharge[t]-Q_dot_charge[t] + P_thermal[t],
    sense = GRB.EQUAL,
    rhs=0,
    name='thermal_balance1_{}'.format(t)
) for t in range(1,T)}



constraints_state_of_charge = {t: m.addConstr(
    lhs =E_t[t+1],
    sense = GRB.EQUAL,
    rhs=E_t[t]+(time_step_size/60)*(Q_dot_charge[t] - Q_dot_discharge[t]),
    name='State_of_charge_{}'.format(t)
) for t in range(0,T-1)}


constraints_storage_temperature = {t: m.addConstr(
    lhs =T_sto[t],
    sense = GRB.EQUAL,
    rhs=T_sto[t-1]+(E_t[t]-E_t[t-1])/(mass_of_storage*cp),
    name='current_temperature_{}'.format(t)
) for t in range(1,T)}

 # <= contraints
constraints_min_state_of_charge = {t: m.addConstr(
    lhs = 0,
    sense = GRB.LESS_EQUAL,
    rhs=E_t[t],
    name='max_constraint1_{}'.format(t)
    ) for t in range(0,T)}

 #>= contraints

constraints_max_state_of_charge= {t: m.addConstr(
    lhs =700,
    sense = GRB.GREATER_EQUAL,
    rhs=E_t[t],
    name='min_constraint2_{}'.format(t)
     ) for t in range(0,T)}

# <= contraints
constraints_min_charge_rate = {t: m.addConstr(
    lhs = 0,
    sense = GRB.LESS_EQUAL,
    rhs=Q_dot_charge[t],
    name='max_constraint2_{}'.format(t)
    ) for t in range(0,T)}

# <= contraints
constraints_min_discharge_rate = {t: m.addConstr(
    lhs = 0,
    sense = GRB.LESS_EQUAL,
    rhs=Q_dot_discharge[t],
    name='max_constraint3_{}'.format(t)
    ) for t in range(0,T)}


 # <= contraints
constraints_minTemperature = {t: m.addConstr(
    lhs = min_temperature,
    sense = GRB.LESS_EQUAL,
    rhs=T_sto[t]+nu[t],
    name='max_constraint1_{}'.format(t)
    ) for t in range(0,T)}

 #>= contraints

constraints_maxTemperature= {t: m.addConstr(
    lhs =max_temperature,
    sense = GRB.GREATER_EQUAL,
    rhs=T_sto[t],
    name='min_constraint_{}'.format(t)
     ) for t in range(0,T)}


#Constraint interface CHP bess 

#charging constraints 
constraints_charging_power = {t: m.addConstr(
    lhs = chargingPower[t], 
    sense = GRB.LESS_EQUAL,
    rhs= P_available[t] ,
    name='chargingPower_constraint{}'.format(t)) 
    for t in set_T}


#constraints Power from CHP to electric load 
constraints_energyDemand={t: m.addConstr(
    lhs = sigma_t[t]*P_chp_l[t]+ dischargingPower[t] ,
    sense = GRB.EQUAL,
    rhs= baseload_Model[t] ,
    name='energyDemand_Constraint{}'.format(t))
    for t in set_T} # type: ignore 

#Constraint SoC of BESS 
constraints_SOC={t: m.addConstr(
    lhs = SOC[t] + charge_efficiency*delta_t*chargingPower[t]-dischargingPower[t]*discharge_efficiency*delta_t,
    sense = GRB.LESS_EQUAL,
    rhs= max_SOC_bess,
    name='Max_SOC_Constraint{}'.format(t)) for t in range(1,T)} 

constraints_SOC_Constraint = {t: m.addConstr(
    lhs=SOC[t+1] ,
    sense = GRB.EQUAL,
    rhs= SOC[t]-dischargingPower[t]*discharge_efficiency + chargingPower[t]*charge_efficiency,
    name='charge_constraint_{}'.format(t)) 
    for t in range(0,T-1)}

constraints_BESS_State = {t: m.addConstr(
    lhs = chargingState[t]+dischargingState[t],
    sense = GRB.LESS_EQUAL,
    rhs= 1 ,name='BESS_State{}'.format(t)) 
    for t in set_T}

constraints_BESS_State1 = {t: m.addConstr(
    lhs = chargingState[t],
    sense = GRB.EQUAL,
    rhs= sigma_t[t] ,name='BESS_State1{}'.format(t)) 
    for t in set_T}

constraints_charging_power3 = {t: m.addConstr(
    lhs = chargingPower[t],
    sense = GRB.LESS_EQUAL,
    rhs=  chargingState[t]*max_ChargingPower ,
    name='chargingPower_constraint_3{}'.format(t)) 
    for t in set_T}

constraints_discharging_power3 = {t: m.addConstr(
    lhs = dischargingPower[t],
    sense = GRB.LESS_EQUAL,
    rhs= dischargingState[t] * max_DischargingPower ,
    name='dischargingPower_constraint_3{}'.format(t)) 
    for t in set_T}


# starting Soc 
constraints_SOC[0]={m.addConstr(
    lhs = SOC[0],
    sense = GRB.EQUAL,
    rhs= min_SOC_bess,
    name='min_Soc_constraint_{}'.format(0))} 

# Defined objective function ---Desmond

#Objective function with Price to run the chp base on Dayahead price 

#objective=gp.quicksum(-P_available[t]* P[t]-chargingPower[t] * P[t] + nu[t]*comfort_fact + sigma_startup[t] * C_startup +sigma_shortdown[t] * C_shortdown + P_fuel[t] * C_fuel    for t in set_T)

"""
This constraint is based on minimizing the cost of operating the CHP and BESS with respect to the market price 
"""

objective = gp.quicksum(-dischargingPower[t]*P[t]*1000 + sigma_startup[t] * C_startup + P_fuel[t] * C_fuel + sigma_shortdown[t] * C_shortdown +nu[t]*comfort_fact for t in set_T)

#objective function with price for battery optimisation 
#objective = gp.quicksum(chargingPower[t] * time_step_size *P[t] - dischargingPower[t]* time_step_size *P[t] + P_chp_l[t] * time_step_size *P[t] for t in set_T) 
m.ModelSense = GRB.MINIMIZE
m.setObjective(objective)
# Solve the optimization problem
m.optimize()


# Extracting values from optimization results
P_thermal_values = [m.getVarByName(varname.VarName).x for varname in P_thermal.values()]
P_available_values = [m.getVarByName(varname.VarName).x for varname in P_available.values()]
chargingState_values = [m.getVarByName(varname.VarName).x for varname in chargingState.values()]
SOC_values = [m.getVarByName(varname.VarName).x for varname in SOC.values()]


Q_charge_values = [m.getVarByName(varname.VarName).x for varname in Q_dot_charge.values()]
Q_discharge_values = [m.getVarByName(varname.VarName).x for varname in  Q_dot_discharge.values()]
dischargePower_values = [m.getVarByName(varname.VarName).x for varname in dischargingPower.values()]
dischargestate_values = [m.getVarByName(varname.VarName).x for varname in dischargingState.values()]
E_t_values = [m.getVarByName(varname.VarName).x for varname in E_t.values()]
# Plotting E_t and sigma_t on the same graph with different y-axes

# Create time axis for plotting
time_axis = range(len(P))

# Create subplots
fig, axs = plt.subplots(3, 1, figsize=(10, 8), sharex=True)

# Plot State of Charge (Thermal Storage)
# Plot Thermal Demand (Q_demand)
axs[0].plot(time_axis, [P[t] for t in set_T], color='blue', label='Price')
axs[0].set_ylabel('Price(EUR/MWh)')
axs[0].grid(True)
axs[0].legend()

# Plot CHP operation (sigma_values)
axs[1].plot(time_axis, P_available_values, color='red', label='Electrical Power')
axs[1].set_ylabel('Electrical Power(kW)')
axs[1].grid(True)
axs[1].legend()

# Plot Heat Pump operation (x_vars_values)
axs[2].plot(time_axis, SOC_values, color='green', label='SoC Battery')
axs[2].set_xlabel('Time')
axs[2].set_ylabel('SoC Battery(kWh)')
axs[2].grid(True)
axs[2].legend()

# Add a title
plt.suptitle('Price, Electrical Power from CHP, SoC of Battery for 10 Days ')

# Adjust layout
plt.tight_layout()
plt.show()