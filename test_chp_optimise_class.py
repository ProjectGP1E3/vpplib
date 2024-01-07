import pandas as pd
import numpy as np
import gurobipy as gp
from gurobipy import GRB
import matplotlib.pyplot as plt
from vpplib.environment import Environment
from vpplib.user_profile import UserProfile

class CHPModel:
    def __init__(self):
        
        self.initialize_parameters()
        self.create_instances()
        self.P_actual = []

    def initialize_parameters(self):
        self.C_fuel = 12.5  # Fuel cost [Euro=kwh]
        self.C_startup = 10  # Costs caused by increased machine wear during switching operations [Euro=kwh]
        self.C_shortdown = 1000
        self.P_max = 4  # Maximum electrical power [kw]
        self.eta_total = 0.8  # Total efficiency of the CHP
        self.delta_t = 15  # Time step
        self.t_total = 31 * 24  # Total time in hrs
        self.target_temperature = 50  # Set your target temperature here
        self.max_ramp_up = 0.5  # Example maximum ramp-up rate in kW per time step
        self.max_ramp_down = 0.7  # Example maximum ramp-down rate in kW per time step
        self.thermal_energy_loss_per_day = 0.13
        self.comfort_fact = 0.01
        self.hysteresis = 5


        self.thermal_energy_demand_yearly = 2500  # Replace with the actual value you intend to use
        self.building_type = "DE_HEF33"
        self.t_0 = 40  # °C

        self.T_on = 5
        self.T_off = 2

        self.efficiency_per_timestep = 1 - (
                self.thermal_energy_loss_per_day
                / (24 * (60 / 15)))

        self.T = int(self.t_total * 60 // self.delta_t)  # Time horizon
        self.c = 0.3  
        self.k = 1.2  
        self.f_1 = 0.96  
        self.f_2 = 0.24  
        self.g = 0.001
        self.eta_charge = 0.9
        self.cp = 4.2
        self.mass_of_storage = 500

        # Values for environment
        self.start = "2015-01-01 12:00:00"
        self.end = "2015-01-14 23:45:00"
        self.year = "2015"
        self.time_freq = "15 min"
        self.timebase = 15


    def create_instances(self):
        # Create instances of environment and user profile
        self.environment = Environment(
            timebase=self.timebase, start=self.start, end=self.end, year=self.year, time_freq=self.time_freq
        )

        self.user_profile = UserProfile(
        identifier=None,
        latitude=None,
        longitude=None,
        thermal_energy_demand_yearly=self.thermal_energy_demand_yearly,
        building_type=self.building_type,
        comfort_factor=None,
        t_0=self.t_0,
        )


    def optimize(self):
        
        prices = self.environment.get_price_data()
        thermal_demand = self.user_profile.get_thermal_energy_demand_hourly()

        # Take 100hrs of the Data
        thermal_demand_use = thermal_demand.iloc[0:self.t_total, 0].values
        prices_use = prices.iloc[0:self.t_total, 0].values

        set_T = range(0, self.T - 1)

        # Create variables
        P = {t: prices_use[(t * self.delta_t // 60)] for t in set_T}
        Q_demand = {t: thermal_demand_use[(t * self.delta_t // 60)] for t in set_T}

        # Initialization of optimization process
        # Create models
        m = gp.Model('MIP')

        max_T_on_off = max(self.T_on, self.T_off)

        # Defining decision variables
        P_available = {t: m.addVar(vtype=GRB.CONTINUOUS, name=f"P_available_{t}") for t in set_T}
        P_fuel = {t: m.addVar(vtype=GRB.CONTINUOUS, name=f"P_fuel_{t}") for t in set_T}
        P_thermal = {t: m.addVar(vtype=GRB.CONTINUOUS, name=f"P_thermal_{t}") for t in set_T}
        sigma_t = {t: m.addVar(vtype=GRB.BINARY, name=f"sigma_{t}") for t in set_T}
        E_t = {t: m.addVar(vtype=GRB.CONTINUOUS, name=f"E_{t}") for t in set_T}
        T_current = {t: m.addVar(vtype=GRB.CONTINUOUS, name=f"Current_Temperature_{t}") for t in set_T}
        sigma_startup = {t: m.addVar(vtype=GRB.BINARY, name=f"sigma_startup_{t}") for t in set_T}
        sigma_shortdown = {t: m.addVar(vtype=GRB.BINARY, name=f"sigma_shortdown_{t}") for t in set_T}

        
        constraints_operating_state = {t: m.addConstr(
            lhs=P_available[t],
            sense=GRB.EQUAL,
            rhs=sigma_t[t] * self.P_max,
            name=f'operating_state_{t}'
        ) for t in range(0, self.T - 1)}

        constraints_power_dependency = {t: m.addConstr(
            lhs = P_fuel[t],
            sense = GRB.EQUAL,
            rhs= self.c*sigma_t[t] + self.k*P_available[t],
            name='Power_dependency_{}'.format(t)
        ) for t in range(0,self.T-1)}

        constraints_Cogeneration = {t: m.addConstr(
            lhs = P_thermal[t],
            sense = GRB.EQUAL,
            rhs= self.f_1*P_available[t] + self.f_2*sigma_t[t],
            name='Cogeneration_{}'.format(t)
        ) for t in range(0,self.T-1)}


        constraints_thermal_balance = {t: m.addConstr(
            lhs =E_t[t+1],
            sense = GRB.EQUAL,
            rhs=E_t[t] - self.efficiency_per_timestep*(self.delta_t/60)*(Q_demand[t]-P_thermal[t]),
            name='thermal_balance_{}'.format(t)
        ) for t in range(0,self.T-2)}

        constraints_current_temperature = {t: m.addConstr(
            lhs =self.mass_of_storage*self.cp*(T_current[t] +273.15),
            sense = GRB.EQUAL,
            rhs=E_t[t],
            name='thermal_balance2_{}'.format(t)
        ) for t in range(0,self.T-1)}

        # >= contraints

        constraints_startup_eq = {t: m.addConstr(
            lhs = sigma_startup[t],
            sense = GRB.GREATER_EQUAL,
            rhs=sigma_t[t]-sigma_t[t-1],
            name='start_up_{}'.format(t)
        ) for t in range(1,self.T-1)}

        constraints_shortdown_eq = {t: m.addConstr(
            lhs = sigma_shortdown[t],
            sense = GRB.GREATER_EQUAL,
            rhs=sigma_t[t-1]-sigma_t[t],
            name='short_down_{}'.format(t)
        ) for t in range(1,self.T-1)}


        # <= contraints
        constraints_rampup_eq = {t: m.addConstr(
            lhs =P_available[t-1]-P_available[t],
            sense = GRB.LESS_EQUAL,
            rhs=4,
            name='max_constraint_{}'.format(t)
            ) for t in range(1,self.T-1)}


        # <= contraints
        constraints_rampdown_eq = {t: m.addConstr(
            lhs =P_available[t]-P_available[t-1],
            sense = GRB.LESS_EQUAL,
            rhs=4,
            name='max_constraint_{}'.format(t)
            ) for t in range(1,self.T-1)}

        # Set objective
        objective = gp.quicksum(
            -P_available[t] * P[t] + sigma_startup[t] * self.C_startup + sigma_shortdown[t] * self.C_shortdown + P_fuel[t] * self.C_fuel
            for t in set_T
        )
        m.ModelSense = GRB.MINIMIZE
        m.setObjective(objective)

        # Optimize the model
        m.optimize()

        # Retrieve and print results
        for t, varname in enumerate(P_fuel.values()):
            self.P_actual.append(m.getVarByName(varname.VarName).x)

        # Calculate and print total power
        power = 0
        for t, varname in enumerate(P_available.values()):
            power += m.getVarByName(varname.VarName).x * self.delta_t / 60
        print(power)


    def plot_results(self):
    # Assuming you have results stored in P_actual list
       plt.figure(figsize=(8, 6))
       plt.plot(self.P_actual[:3000])  # Plotting the first 3000 time steps
       plt.xlabel('Time Steps')
       plt.ylabel('Q_demand')
       plt.title('Thermal Demand (Q_demand) over Time (First 3000 steps)')
       plt.grid(True)
       plt.show()


if __name__ == "__main__":
    chp_optimizer = CHPModel()
    chp_optimizer.optimize()
    chp_optimizer.plot_results()
