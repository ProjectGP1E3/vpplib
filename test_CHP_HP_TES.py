import pandas as pd
import numpy as np
import gurobipy as gp
from gurobipy import GRB
import matplotlib.pyplot as plt
from vpplib.environment import Environment
from vpplib.user_profile import UserProfile
from plotDataGenerator import *



# Parameters to be defined for CHP unit 
C_fuel = 12.5  # Fuel cost [Euro=kwh]
C_startup = 10  # Costs caused by increased machine wear during switching on operations [Euro=kwh]
C_shortdown=10  # Costs caused by increased machine wear during  switching off operations [Euro=kwh]
T_on=1  # minimum runtime of CHP
T_off=2 # minimum off time of CHP
P_nom=4   #nominal electrical power in kw 
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
storage_efficiency=0.00057  #in   0.057%
static_efficiency=0.00056   #in 0.056 %
charge_efficiency=0.9    # in 90%
discharge_efficiency= 0.9  # in 90%
max_chare_rate= 0.25    # in 25%
max_discharge_rate =0.25  # in 25%
max_storage_cap=250 #KW
start_E_t=112.5
Max_E_t=250

thermal_energy_loss_per_day = 0.13
efficiency_per_timestep = 1 - (
            thermal_energy_loss_per_day
            / (24 * (60 /15)))

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
# Define the maximum number of startups
N = 5  # Adjust this value as per your requirements

#Parameter to be defined for Enviroment
start = "2015-01-01 00:00:00"
end = "2015-01-10 23:45:00"
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

#take 240hrs of the Data 
thermal_demand_use = thermal_demand.iloc[0:num_hours, 0].values  #check  shape
prices_use=prices.iloc[0:num_hours,0].values     #check shape 
mean_temp_hours_use = mean_temp_hours.iloc[0:num_hours, 0].values #check shape

#create variables 
T_a = {t: mean_temp_hours_use[(t *time_step_size)//60] for t in set_T}  #ambient temperature

P = {t: prices_use[(t *time_step_size)//60] for t in set_T}  #check len 960 for 10days

Q_demand={t:thermal_demand_use[(t *time_step_size//60)] for t in set_T}  #heat demand in kw

# Defining decision variables
P_available = {t:m.addVar(vtype=GRB.CONTINUOUS, name="P_available_{}".format(t)) for t in set_T} #Actual available electrical output power of the CHP [kW]

P_fuel={t:m.addVar(vtype=GRB.CONTINUOUS, name="P_fuel_{}".format(t)) for t in set_T} # fuel consumption of the CHP[KW]

P_thermal={t:m.addVar(vtype=GRB.CONTINUOUS, name="P_thermal{}".format(t)) for t in set_T} #Thermal output power of the CHP [kW]

sigma_t = {t: m.addVar(vtype=GRB.BINARY, name="sigma_{}".format(t)) for t in set_T}

E_t={t:m.addVar(vtype=GRB.CONTINUOUS, name="E_{}".format(t)) for t in set_T}# state of charge[KWh] of TES

sigma_startup= {t:m.addVar(vtype=GRB.BINARY, name="sigma_startup_{}".format(t)) for t in set_T} #  Start-up process in t

sigma_shortdown= {t:m.addVar(vtype=GRB.BINARY, name="sigma_shortdown_{}".format(t)) for t in set_T} #  Start-up process in t

Q_dot_charge={t:m.addVar(vtype=GRB.CONTINUOUS, name="Q_dot_charge_{}".format(t)) for t in set_T}# charging rate [KW]

Q_dot_discharge={t:m.addVar(vtype=GRB.CONTINUOUS, name="Q_dot_discharge_{}".format(t)) for t in set_T}# discharging rate [KW]

T_sto={t:m.addVar(vtype=GRB.CONTINUOUS, name="Current_Temperature_{}".format(t)) for t in set_T}# storage temperature of TES in °C

Loss_Tes={t:m.addVar(vtype=GRB.CONTINUOUS, name="Loss_ThermalStorage_{}".format(t)) for t in set_T}# loss in TES in kJ

#x_vars = {t:m.addVar(vtype=GRB.CONTINUOUS,lb=0, ub=1, name="x_{}".format(t)) for t in set_T} # operating mode of heat pump
x_vars = {t:m.addVar(vtype=GRB.BINARY, name="x_{}".format(t)) for t in set_T} # operating mode of heat pump

heatpump_startup = {t:m.addVar(vtype=GRB.BINARY, name="heatpump_startup_{}".format(t)) for t in set_T} # startup heat pump

P_hp_thermal={t:m.addVar(vtype=GRB.CONTINUOUS, name="P_hp_thermal_{}".format(t)) for t in set_T} #thermal power of heat pump in[kW]

P_hp_Elec={t:m.addVar(vtype=GRB.CONTINUOUS, name="P_hp_Elec_{}".format(t)) for t in set_T} #Electricity consumption of heat pump in[kW]

nu = {t:m.addVar(vtype=GRB.CONTINUOUS, name="nu_{}".format(t)) for t in set_T} # thermal disutility in °C

weight_factor=10
#Constraint Equations CHP

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

constraints_thermal_generation = {t: m.addConstr(
    lhs = P_hp_thermal[t],
    sense = GRB.EQUAL,
    rhs=x_vars[t]*heat_pump_power(P_nom, T_a[t]) ,
    name='Thermalgeneration_{}'.format(t)
) for t in range(0,T)}

#Constraint Equations Thermal storage interface CHP

constraints_thermal_balance1 = {t: m.addConstr(
    lhs =-Q_demand[t] + Q_dot_discharge[t]-Q_dot_charge[t] + P_thermal[t] + P_hp_thermal[t],
    sense = GRB.EQUAL,
    rhs=0,
    name='thermal_balance1_{}'.format(t)
) for t in range(1,T)}



constraints_state_of_charge = {t: m.addConstr(
    lhs =E_t[t],
    sense = GRB.EQUAL,
    rhs=E_t[t-1]+charge_efficiency*Q_dot_charge[t] - Q_dot_discharge[t]/discharge_efficiency -Loss_Tes[t],
    name='State_of_charge_{}'.format(t)
) for t in range(1,T)}

constraints_Loss_Thermal = {t: m.addConstr(
    lhs =Loss_Tes[t],
    sense = GRB.EQUAL,
    rhs=storage_efficiency*E_t[t-1],
    name='current_temperature_{}'.format(t)
) for t in range(1,T)}


#Constraint Equations Heat pump


#operation of heat pump 
constraints_startup_eq1 = {t: m.addConstr(
    lhs = heatpump_startup[t],
    sense = GRB.GREATER_EQUAL,
    rhs=x_vars[t]-x_vars[t-1],
    name='start_up1_{}'.format(t)
) for t in range(1,T)}

constraints_startup_eq2 = {t: m.addConstr(
    lhs = heatpump_startup[t],
    sense = GRB.LESS_EQUAL,
    rhs=1-x_vars[t-1],
    name='start_up2_{}'.format(t)
) for t in range(1,T)}

# Add the constraint for the maximum number of startups
m.addConstr(
    gp.quicksum(heatpump_startup[t] for t in set_T) <= N,
    name="max_startup_constraint"
)

constraints_startup_eq3 = {t: m.addConstr(
    lhs = heatpump_startup[t],
    sense = GRB.LESS_EQUAL,
    rhs=x_vars[t],
    name='start_up3_{}'.format(t)
) for t in range(0,T)}

constraints_Electrical_Consumption = {t: m.addConstr(
    lhs = P_hp_Elec[t],
    sense = GRB.EQUAL,
    rhs=el_power*x_vars[t] ,
    name='ElectricalConsumption_{}'.format(t)
) for t in range(0,T)}

constraints_operation = {t: m.addConstr(
    lhs = x_vars[t]+sigma_t[t],
    sense = GRB.LESS_EQUAL,
    rhs=1,
    name='Operation_{}'.format(t)
) for t in range(0,T)}



#Constraint Equation storage Temperature TES

constraints_storage_temperature = {t: m.addConstr(
    lhs =T_sto[t],
    sense = GRB.EQUAL,
    rhs=T_sto[t-1]+ 3600*(E_t[t]-E_t[t-1])/(mass_of_storage*cp),
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
    lhs = Max_E_t,
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

 #>= contraints

constraints_max_charge_rate= {t: m.addConstr(
    lhs =max_storage_cap*max_chare_rate,
    sense = GRB.GREATER_EQUAL,
    rhs=charge_efficiency*Q_dot_charge[t]+ 0.001*k_sto*A_sto*(min_temperature-T_a[t]),
    name='min_constraint4_{}'.format(t)
     ) for t in range(0,T)}
# <= contraints
constraints_min_discharge_rate = {t: m.addConstr(
    lhs = 0,
    sense = GRB.LESS_EQUAL,
    rhs=Q_dot_discharge[t],
    name='max_constraint3_{}'.format(t)
    ) for t in range(0,T)}

constraints_max_discharge_rate= {t: m.addConstr(
    lhs =discharge_efficiency*max_storage_cap*max_discharge_rate,
    sense = GRB.GREATER_EQUAL,
    rhs=Q_dot_discharge[t],
    name='min_constraint5_{}'.format(t)
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
    lhs =maximum_temperature,
    sense = GRB.GREATER_EQUAL,
    rhs=T_sto[t],
    name='min_constraint_{}'.format(t)
     ) for t in range(0,T)}

# = constraint
constraints_state_of_charge[0] = m.addConstr(
    lhs=E_t[0] ,
    sense = GRB.EQUAL,
    rhs= start_E_t,
    name='State_of_charge_{}'.format(0)) 

constraints_storage_temperature [0] = m.addConstr(
    lhs=T_sto[0] ,
    sense = GRB.EQUAL,
    rhs= min_temperature,
    name='current_temperature_{}'.format(0)) 
# Objective

objective=gp.quicksum(-P_available[t] * P[t] + P_hp_Elec[t]*P[t]  + 1000*nu[t]*comfort_fact + 10*heatpump_startup[t]+sigma_startup[t] * C_startup +sigma_shortdown[t] * C_shortdown + P_fuel[t] * C_fuel    for t in set_T)

m.setObjective(objective)

m.ModelSense = GRB.MINIMIZE

 # Solve the optimization problem
m.optimize()


# Extracting values from optimization results
x_vars_values = [m.getVarByName(varname.VarName).x for varname in x_vars.values()]
sigma_values = [m.getVarByName(varname.VarName).x for varname in sigma_t.values()]
E_t_values = [m.getVarByName(varname.VarName).x for varname in E_t.values()]
Price = [P[t] for t in set_T]
Q_demand_values = [Q_demand[t] for t in set_T]

P_hp_thermal_values = [m.getVarByName(varname.VarName).x for varname in P_hp_thermal.values()]

P_hp_Elec_values = [m.getVarByName(varname.VarName).x for varname in P_hp_Elec.values()]

P_thermal_values = [m.getVarByName(varname.VarName).x for varname in  P_thermal.values()]

P_available_values = [m.getVarByName(varname.VarName).x for varname in  P_available.values()]

Q_dot_discharge_values = [m.getVarByName(varname.VarName).x for varname in Q_dot_discharge.values()]

Q_dot_charge_values = [m.getVarByName(varname.VarName).x for varname in Q_dot_charge.values()]

T_current_values = [m.getVarByName(varname.VarName).x for varname in T_sto.values()]

E_percentage = [(E_t / Max_E_t) * 100 for E_t in E_t_values]

Thermal_loss=[m.getVarByName(varname.VarName).x for varname in Loss_Tes.values()]

# Create time axis for plotting
time_axis = range(len(P))
date_series = plotDataGenerator(start, end, time_freq, time_freq)

# Create subplots
def plot(x, y1, y2, y3, y1_label, y2_label, y3_label, legend_1, legend_2, legend_3, title):
    fig, axs = plt.subplots(3, 1, figsize=(10, 8), sharex=True)

    axs[0].plot(x, y1, color='red', label=legend_1)
    axs[0].set_ylabel(y1_label)
    axs[0].grid(True)
    axs[0].legend()

    axs[1].plot(x, y2, color='blue', label=legend_2)
    axs[1].set_ylabel(y2_label)
    axs[1].grid(True)
    axs[1].legend()

    axs[2].plot(x, y3, color='green', label=legend_3)
    #axs[2].plot(x, y4, color='brown', label=legend_4)
    axs[2].set_xlabel('Time')
    axs[2].set_ylabel(y3_label)
    axs[2].grid(True)
    axs[2].legend()

    # Add a title
    plt.suptitle(title)

    # Adjust layout
    plt.tight_layout()
    plt.show()

#plot(x, y1, y2, y3, y1_label, y2_label, y3_label, legend_1, legend_2, legend_3, title)
plot(date_series, Price, sigma_values, x_vars_values, 
     "Price(EUR/MWh)", "CHP Operation", "Heat Pump Operation", 
     "Price", "CHP Operation", "Heat Pump Operation", 
     "Optimal operation of CHP and Heat Pump along with Electricity price")

#plot(x, y1, y2, y3, y1_label, y2_label, y3_label, legend_1, legend_2, legend_3, title)
plot(date_series,Q_demand_values, P_hp_thermal_values, P_thermal_values, 
     "Heat demand(kW)", "Thermal Power(Kw)", "Thermal Power(kW)", 
     "Heat demand", "Thermal Power HP", "Thermal Power CHP", 
     "Heat demand, Thermal power generated by Heat pump and CHP")

#plot(x, y1, y2, y3, y1_label, y2_label, y3_label, legend_1, legend_2, legend_3, title)
plot(date_series, sigma_values, x_vars_values, Q_dot_charge_values, 
     "CHP operation", "Heat pump operation", "charge rate(kW)", 
     "CHP operation ", "Heat pump operation", "charge rate", 
     "Optimal operation of CHP, HP along with charge rate of Thermal storage")

#plot(x, y1, y2, y3, y1_label, y2_label, y3_label, legend_1, legend_2, legend_3, title)
plot(date_series, E_percentage, P_hp_thermal_values, x_vars_values, 
     "State of Charge(%)", "Thermal Power(kW)", "Heat Pump Operation", 
     "State of Charge of TES ", "Thermal Power HP", "Heat Pump Operation", 
     "Optimal operation of Heat Pump, Thermal heat generated along with SOC of Thermal storage")

#plot(x, y1, y2, y3, y1_label, y2_label, y3_label, legend_1, legend_2, legend_3, title)
plot(date_series, Price, P_available_values, P_hp_Elec_values, 
     "Price(Eur/Mwh)", "Electrical Power CHP(kW)", "Electrical Power HP(kW)", 
     "Price", "Electrical Power CHP", "Electrical Power Heat Pump", 
     "Price along with Electrical power generated by CHP and consumed by Heatpump")