from hamcrest import none
from matplotlib import style
from matplotlib.lines import drawStyles, lineStyles
from torch import t
from vpplib.user_profile import UserProfile
from vpplib.environment import Environment
from vpplib.electrical_energy_storage import ElectricalEnergyStorage
from vpplib.photovoltaic import Photovoltaic

from vpplib.heat_pump import HeatPump
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import gurobipy as gp
from gurobipy import GRB

class PvBessOptimization():
    def __init__(self):
        self.intialize_pvbess_parameters()
    
    def intialize_pvbess_parameters(self):

        # Battery Variables Initialization
        self.maxChargingPower=0.1
        self.maxDischargingPower=0.09
        self.dischargingEfficiency=0.9
        self.chargingEfficiency=0.9
        self.minimumSoC=5
        self.maximumSoC=40
        self.startSoC=10
        self.max_power = 40 # kW
        self.capacity = 40  # kWh
        self.max_c = 1

        # Values for environment
        self.start = "2015-05-01 12:00:00"
        self.end = "2015-05-01 23:45:00"
        self.number_of_days=1
        self.year = "2015"
        self.time_freq = "15 min"
        self.timebase = 15


        # Environment initialization
        self.environment = Environment(
            timebase=self.timebase,
            start=self.start,
            end=self.end,
            year=self.year,
            time_freq=self.time_freq,
        )


        # Values for user_profile
        self.latitude = 50.941357
        self.longitude = 6.958307
        self.building_type = "DE_HEF33"
        self.t_0 = 40

        #User profile Initialization
        self.user_profile = UserProfile(
            identifier=None,
            latitude=self.latitude,
            longitude=self.longitude,
            building_type=self.building_type,
            comfort_factor=None,
            t_0=self.t_0,
        )
        

        # PV
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

        pv = Photovoltaic(
            unit=unit,
            identifier=(name + "_pv"),
            environment=self.environment,
            user_profile=self.user_profile,
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
         # creating an ESS
        ESS = ElectricalEnergyStorage(
            unit=unit,
            identifier=(name + "_storage"),
            environment=self.environment,
            user_profile=self.user_profile,
            capacity=self.capacity,
            charge_efficiency=self.chargingEfficiency,
            discharge_efficiency=self.dischargingEfficiency,
            max_power=self.max_power,
            max_c=self.max_c,
        )

        
        self.environment.get_pv_data(file="./input/pv/dwd_pv_data_2015.csv")
        pv.prepare_time_series()
        self.pvPower=pv.timeseries.loc[self.start:self.end]

        baseload = pd.read_csv("./input/baseload/df_S_15min.csv")
        baseload.drop(columns=["Time"], inplace=True)
        baseload.set_index(self.environment.pv_data.index, inplace=True)

        # combine baseload and pv timeseries to get residual load
        house_loadshape = pd.DataFrame(baseload["0"].loc[self.start:self.end] / 1000)
        house_loadshape["pv_gen"] = self.pvPower.loc[self.start:self.end]
        house_loadshape["Excess_Power"] = ( self.pvPower.PVbus_pv-(baseload["0"].loc[self.start:self.end] / 1000) )#type :ignore
        ExcessPower=house_loadshape.Excess_Power

        
        self.pvPower_use=ExcessPower # type: ignore
        self.systemLoad=-1*self.pvPower_use
        self.systemLoad[self.systemLoad<0]=0
        self.outputLoad=1*self.systemLoad
        self.outputLoad[self.outputLoad>self.maxDischargingPower]=self.maxDischargingPower
        self.pvPower_use[self.pvPower_use<0]=0

     
        self.prices = self.environment.get_price_data()

    def pvbess_model(self):
        time_step_size = 15
        number_of_days = 1
        num_hours=number_of_days*24
        num_time_step=int(num_hours*60//time_step_size)
        T = num_time_step
        set_T = range(0,T-1)
        timestep=15

       
        
        # Create models
        m = gp.Model('MIP')
        m.setParam('TimeLimit',5*60)


        prices_use=self.prices.iloc[40:num_hours+40, 0].values
        

        priceModel = {t: prices_use[(t *time_step_size)//60] for t in set_T}
        pvPowerModel= {t: self.pvPower_use[(t *time_step_size)//60] for t in set_T}
        loadModel= {t: self.outputLoad[(t *time_step_size)//60] for t in set_T}
        systemLoadModel={t: self.systemLoad[(t *time_step_size)//60] for t in set_T}
        chargingPower = {t:m.addVar(vtype=GRB.CONTINUOUS,lb=0,ub=self.maxChargingPower,name="chargingPower_{}".format(t)) for t in set_T}
        dischargingPower = {t:m.addVar(vtype=GRB.CONTINUOUS,lb=0,ub=self.maxDischargingPower,name="dischargingPower_{}".format(t)) for t in set_T}
        chargingState = {t:m.addVar(vtype=GRB.INTEGER,lb=0,ub=1,name="chargingState_{}".format(t)) for t in set_T}
        dischargingState = {t:m.addVar(vtype=GRB.INTEGER ,lb=0,ub=1,name="dischargingState_{}".format(t)) for t in set_T}
        SoC={t:m.addVar(vtype=GRB.CONTINUOUS,lb=self.minimumSoC,ub=self.maximumSoC ,name="chargePercentage_{}".format(t)) for t in set_T}

        ##Constraints on charging process
        #chargingPower constraints
        constraints_eq1={t: m.addConstr(lhs = chargingPower[t],sense = GRB.LESS_EQUAL,rhs= chargingState[t] * self.maxChargingPower ,name='chargingPower_constraint_{}'.format(t)) for t in set_T} # type: ignore 
        #state of charge constraint
        constraints_eq2={t: m.addConstr(lhs = SoC[t-1] + self.chargingEfficiency*timestep*chargingPower[t],sense = GRB.LESS_EQUAL,rhs= self.maximumSoC,name='chargingState_constraint_{}'.format(t)) for t in range(1,T-1)} # type: ignore
        constraints_eq7={t: m.addConstr(lhs = chargingPower[t],sense = GRB.LESS_EQUAL,rhs= pvPowerModel[t] ,name='chargingPowerPV_constraint_{}'.format(t)) for t in set_T} # type: ignore
        # Constraints on discharging process
        #chargingPower constraints
        constraints_eq3={t: m.addConstr(lhs = dischargingPower[t],sense = GRB.LESS_EQUAL,rhs= dischargingState[t] * self.maxDischargingPower ,name='dischargingPower_constraint_{}'.format(t)) for t in set_T} # type: ignore
        constraints_eq8={t: m.addConstr(lhs = dischargingPower[t],sense = GRB.GREATER_EQUAL,rhs= dischargingState[t] *loadModel[t] ,name='dischargingPowerPV_constraint_{}'.format(t)) for t in set_T} # type: ignore
        #state of charge constraint
        constraints_eq4={t: m.addConstr(lhs = SoC[t-1] - (1/self.dischargingEfficiency)*timestep*dischargingPower[t],sense = GRB.GREATER_EQUAL,rhs= self.minimumSoC ,name='dischargingState_constraint_{}'.format(t)) for t in range(1,T-1)} # type: ignore

        #Constraints on Processes
        constraints_eq5={t: m.addConstr(lhs = chargingState[t]+dischargingState[t],sense = GRB.LESS_EQUAL,rhs= 1 ,name='chargingDischargingCorrelation_constraint_{}'.format(t)) for t in set_T} # type: ignore

        #Constraints on Charge
        constraints_eq6=   {t: m.addConstr(lhs=SoC[t] ,sense = GRB.EQUAL,rhs= SoC[t-1]+self.chargingEfficiency*timestep*chargingPower[t]-timestep*(1/self.dischargingEfficiency)*dischargingPower[t],name='charge_constraint_{}'.format(t)) for t in range(1,T-1)} # type: ignore
        constraints_eq6[0]=    m.addConstr(lhs=SoC[0] ,sense = GRB.EQUAL,rhs= self.startSoC,name='charge_constraint_{}'.format(0)) # type: ignore

        objective = gp.quicksum(-1 * chargingPower[t] * timestep * self.prices.iloc[t, 0] + (dischargingPower[t] - dischargingState[t] *loadModel[t])* timestep * self.prices.iloc[t, 0] + (pvPowerModel[t] )* timestep * self.prices.iloc[t, 0]for t in set_T) # type: ignore

        m.ModelSense = GRB.MAXIMIZE
        m.setObjective(objective)
        # Solve the optimization problem
        m.optimize()

        # Extracting timeseries
        charging_power_values = [chargingPower[t].X for t in set_T]
        discharging_power_values = [dischargingPower[t].X for t in set_T]
        systemLoad_values=[ systemLoadModel[t] for t in set_T]
        SoC_values = [SoC[t].X for t in range(1, T-1)]  # Starting from 1 because we don't have charge[0]
        SoC_values.insert(0,self.startSoC)
        time_steps = list(set_T)

        plt.figure(figsize=(12, 6))

        # Plotting Charging Power
        plt.subplot(3, 1, 1)
        plt.plot(time_steps,charging_power_values, label='charging Power',drawstyle='steps')
        plt.ylabel('Power (kW)')
        plt.title('charging Power over Time')
        plt.legend()

        # Plotting Discharging Power
        plt.subplot(3, 1, 2)
        plt.plot(time_steps, discharging_power_values, label='Discharging Power',drawstyle='steps')
        plt.ylabel('Power (kW)')
        plt.title('Discharging Power over Time')
        plt.legend()

        # Plotting Charge Percentage
        plt.subplot(3, 1, 3)
        plt.plot(time_steps, SoC_values, label='Charge ')
        plt.xlabel('Time Step')
        plt.ylabel('Charge ')
        plt.title('Battery Charge over Time')
        plt.legend()

        plt.tight_layout()

        #print(pvPowerModel)
        #print(systemLoad_values)
        plt.show()
        # ESS.residual_load=house_loadshape.residual_load
        # ESS.prepare_time_series()
        # print("prepare_time_series:")
        # print(ESS.timeseries.head())
        # ESS.timeseries.plot(figsize=(16, 9))
        # plt.show()


        #residuals and discharging
        fig, ax1 = plt.subplots(figsize=(10, 5))

        # Plotting prices on the primary y-axis
        ax1.plot(list(loadModel.keys()), list(loadModel.values()), label='residuals', color='b')
        ax1.set_ylabel('residuals', color='b')
        ax1.tick_params(axis='y', labelcolor='b')

        # Creating a secondary y-axis for discharging power
        ax2 = ax1.twinx()  
        ax2.plot(SoC_values, label='SOC', color='g')
        ax2.set_ylabel('SOC', color='g')
        ax2.tick_params(axis='y', labelcolor='g')

        # Adding legend
        ax1.legend(loc='upper left')
        ax2.legend(loc='upper right')

        # Display the plot
        plt.show()

        #Plots on same axis charging, discharging, SOC
        fig, ax1 = plt.subplots(figsize=(12, 6))

        discharging_power_values = [-value for value in discharging_power_values]

        # Plotting Charging Power as positive bars
        ax1.bar(time_steps, charging_power_values, width=0.4, label='Charging Power', color='blue')

        # Plotting Discharging Power as negative bars
        ax1.bar(time_steps, discharging_power_values, width=0.4, label='Discharging Power', color='orange')

        # Creating a secondary y-axis for the SOC
        ax2 = ax1.twinx()

        # Plotting the SOC on the secondary y-axis
        ax2.plot(time_steps, SoC_values, label='SOC', color='black', linestyle='-')

        # Adding labels, title, and grid
        ax1.set_xlabel('Time Step')
        ax1.set_ylabel('Power (kW)', color='blue')
        ax2.set_ylabel('SOC', color='black')
        plt.title('Charging/Discharging Power and SOC over Time')
        ax1.grid(True)

        # Adding legends
        ax1.legend(loc='upper left')
        ax2.legend(loc='upper right')

        # Making the y-axis label color match the data
        ax1.tick_params(axis='y', labelcolor='blue')
        ax2.tick_params(axis='y', labelcolor='black')

        plt.show()

        #pv and charging
        fig, ax3 = plt.subplots(figsize=(10, 5))

        # Plotting prices on the primary y-axis
        ax3.plot(list(pvPowerModel.keys()), list(pvPowerModel.values()), label='PV', color='b')
        ax3.set_ylabel('PV', color='b')
        ax3.tick_params(axis='y', labelcolor='b')

        # Creating a secondary y-axis for discharging power
        ax4 = ax3.twinx()  
        ax4.plot(SoC_values, label='SOC', color='g')
        ax4.set_ylabel('SOC', color='g')
        ax4.tick_params(axis='y', labelcolor='g')

        # Adding legend
        ax3.legend(loc='upper left')
        ax4.legend(loc='upper right')

        # Display the plot
        plt.show()

if __name__ == "__main__":
    optimization = PvBessOptimization()
    optimization.pvbess_model()