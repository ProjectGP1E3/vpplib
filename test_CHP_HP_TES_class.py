import pandas as pd
import numpy as np
import gurobipy as gp
from gurobipy import GRB
import matplotlib.pyplot as plt
from vpplib.environment import Environment
from vpplib.user_profile import UserProfile


class OptimizationModel:
    def __init__(self):
        
        self.initialize_parameters()
        #self.create_instances()
    
    def initialize_parameters(self):

        # Parameters to be defined for CHP unit 
        self.C_fuel = 12.5  # Fuel cost [Euro=kwh]
        self.C_startup = 10  # Costs caused by increased machine wear during switching on operations [Euro=kwh]
        self.C_shutdown=10  # Costs caused by increased machine wear during  switching off operations [Euro=kwh]
        self.T_on=1  # minimum runtime of CHP
        self.T_off=2 # minimum off time of CHP
        self.P_nom=5   #nominal electrical power in kw 
        self.eta_total = 0.8  # Total efficiency of the CHP
        self.c=0.3 # calculated according Steck PHD thesis see (Steck 2012 page 34)
        self.k=1.2 # calculated according Steck PHD thesis see (Steck 2012 page 34) 
        self.f_1=0.96 # calculated according Steck PHD thesis see (Steck 2012 page 35) 
        self.f_2=0.24 # calculated according Steck PHD thesis see (Steck 2012 page 35)


        #Parameter to be defined for Thermal storage unit 
        self.maximum_temperature = 60  # maximum temperature of TES in °C
        self.min_temperature=40     # minimum temperature of TES in °C
        self.mass_of_storage = 500  # kg  
        self.cp = 4.2      #specific heat capacity of storage in kJ/kg/K
        self.k_sto= 1.12   #  thermal conductivity of storage material W/m^2K
        self.A_sto=3.39    #  Area of storage unit in m^2

        #Parameter to be defined for Heat pump 
        self.heat_pump_type = "Air"
        self.heat_sys_temp = 60
        self.el_power = 5  # nominal electrical power in kw 

        #Parameter to be defined for Enviroment
        self.start = "2015-01-01 12:00:00"
        self.end = "2015-01-14 23:45:00"
        self.year = "2015"
        self.timebase = 15
        self.time_freq = "15 min"

        #Parameter to be defined for user Profile
        self.yearly_thermal_energy_demand = 12500
        self.building_type = "DE_HEF33"
        self.t_0 = 40    # °C

        # Environment and user profile initialization
        self.environment = Environment(
            timebase=self.timebase,
            start=self.start,
            end=self.end,
            year=self.year,
            time_freq=self.time_freq,
        )
        self.user_profile = UserProfile(
            identifier=None,
            latitude=None,
            longitude=None,
            thermal_energy_demand_yearly=self.yearly_thermal_energy_demand,
            building_type=self.building_type,
            comfort_factor=None,
            t_0=self.t_0,
        )

    def heat_pump_power(self, phi_e, tmp):
        """
        Takes an electrical power flow and converts it to a heat flow.

        :param phi_e: The electrical power
        :type phi_e: Float
        :return: Returns the heat flow as an integer
        """
        cop = (
            6.81
            - 0.121 * (self.heat_sys_temp - tmp)
            + 0.00063 * (self.heat_sys_temp - tmp) ** 2
        )
        
        return phi_e * cop

    def build_model(self):
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

        prices = self.environment.get_price_data()  #check the shape to be sure 

        thermal_demand=self.user_profile.get_thermal_energy_demand_hourly()  #check the shape 

        mean_temp_hours = self.environment.get_mean_temp_hours()   #check the shape 

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

        #x_vars = {t:m.addVar(vtype=GRB.CONTINUOUS,lb=0, ub=1, name="x_{}".format(t)) for t in set_T} # operating mode of heat pump
        x_vars = {t:m.addVar(vtype=GRB.BINARY, name="x_{}".format(t)) for t in set_T} # operating mode of heat pump


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
        ) for t in range(1, T - self.T_on-1) for j in range(1, self.T_on+1)}

        # Define constraints downtime
        constraints_downtime_eq = {t: m.addConstr(
            lhs=sigma_t[t-1] - sigma_t[t] +sigma_t[t + j],
            sense=GRB.LESS_EQUAL,
            rhs=1,
            name=f"max_constraint_{t}"
        ) for t in range(1, T - self.T_off-1) for j in range(1, self.T_off+1)}

        constraints_operating_state = {t: m.addConstr(
            lhs = P_available[t],
            sense = GRB.EQUAL,
            rhs= sigma_t[t]*self.P_nom,
            name='operating_state_{}'.format(t)
        ) for t in range(0,T)}

        constraints_power_dependency = {t: m.addConstr(
            lhs = P_fuel[t],
            sense = GRB.EQUAL,
            rhs= self.c*sigma_t[t] + self.k*P_available[t],
            name='Power_dependency_{}'.format(t)
        ) for t in range(0,T)}

        constraints_Cogeneration = {t: m.addConstr(
            lhs = P_thermal[t],
            sense = GRB.EQUAL,
            rhs= self.f_1*P_available[t] + self.f_2*sigma_t[t],
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
            lhs =-Q_demand[t] + Q_dot_discharge[t]-Q_dot_charge[t] + P_thermal[t] + P_hp_thermal[t],
            sense = GRB.EQUAL,
            rhs=0,
            name='thermal_balance1_{}'.format(t)
        ) for t in range(1,T)}



        constraints_state_of_charge = {t: m.addConstr(
            lhs =E_t[t+1],
            sense = GRB.EQUAL,
            rhs=E_t[t]+(time_step_size/60)*(Q_dot_charge[t] - Q_dot_discharge[t]-0.001*self.k_sto*self.A_sto*(T_sto[t]-20)),
            name='State_of_charge_{}'.format(t)
        ) for t in range(0,T-1)}



        #Constraint Equations Heat pump

        constraints_thermal_generation = {t: m.addConstr(
            lhs = P_hp_thermal[t],
            sense = GRB.EQUAL,
            rhs=self.heat_pump_power(self.P_nom, T_a[t])*x_vars[t] ,
            name='Thermalgeneration_{}'.format(t)
        ) for t in range(0,T)}


        constraints_Electrical_Consumption = {t: m.addConstr(
            lhs = P_hp_Elec[t],
            sense = GRB.EQUAL,
            rhs=self.el_power*x_vars[t] ,
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
            rhs=T_sto[t-1]+(E_t[t]-E_t[t-1])/(self.mass_of_storage*self.cp),
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
            lhs = self.min_temperature,
            sense = GRB.LESS_EQUAL,
            rhs=T_sto[t]+nu[t],
            name='max_constraint1_{}'.format(t)
            ) for t in range(0,T)}


        #>= contraints

        constraints_maxTemperature= {t: m.addConstr(
            lhs =self.maximum_temperature,
            sense = GRB.GREATER_EQUAL,
            rhs=T_sto[t],
            name='min_constraint_{}'.format(t)
            ) for t in range(0,T)}


        # Objective

        objective=gp.quicksum(-P_available[t] * P[t] + P_hp_Elec[t]*P[t]  + nu[t]*comfort_fact + sigma_startup[t] * self.C_startup +sigma_shortdown[t] * self.C_shutdown + P_fuel[t] * self.C_fuel    for t in set_T)

        m.setObjective(objective)

        m.ModelSense = GRB.MINIMIZE

        # Solve the optimization problem
        m.optimize()

        # Extracting values from optimization results
        E_values = [m.getVarByName(varname.VarName).x for varname in E_t.values()]
        sigma_values = [m.getVarByName(varname.VarName).x for varname in sigma_t.values()]
        nu_values = [m.getVarByName(varname.VarName).x for varname in nu.values()]


        Q_charge_values = [m.getVarByName(varname.VarName).x for varname in Q_dot_charge.values()]
        Q_discharge_values = [m.getVarByName(varname.VarName).x for varname in  Q_dot_discharge.values()]
        T_current_values = [m.getVarByName(varname.VarName).x for varname in T_sto.values()]


        # Plotting E_t and sigma_t on the same graph with different y-axes
        
        
        fig, ax1 = plt.subplots(figsize=(8, 6))

        # Plotting E_t (state of charge)
        color = 'tab:red'
        ax1.set_xlabel('Time Steps')
        ax1.set_ylabel('State of Charge (E_t)', color=color)
        ax1.plot(T_current_values[:960], color=color)
        ax1.tick_params(axis='y', labelcolor=color)

        # Creating a secondary y-axis for sigma_t (binary variable)++
        ax2 = ax1.twinx()
        color = 'tab:blue'
        ax2.set_ylabel('Binary Variable (sigma_t)', color=color)
        ax2.plot(nu_values[:960], color=color)
        ax2.tick_params(axis='y', labelcolor=color)

        fig.tight_layout()
        plt.title('State of Charge (E_t) and Binary Variable (sigma_t)')
        plt.show()

if __name__ == "__main__":
    optimizer = OptimizationModel()
    optimizer.build_model()

     
       

