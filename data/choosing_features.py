"""
@author: Monse Guedes Ayala
@project: Poisoning Attacks Paper
"""

import pandas as pd
import os
import numpy as np
from sklearn.linear_model import Lasso


class DataSet():
    def __init__(self, name: str):
        self.name = name
        self.file = 'data-binary.csv'
        self.path = os.path.join('data', self.name, self.file) 

        self.create_dataframe()
        self.format_data()

    def create_dataframe(self):
        """
        Create dataframe with dataset
        """

        self.dataframe = pd.read_csv(self.path, index_col=0)

        return self.dataframe

    def format_data(self):
        """
        Convert data to format that sklearn can handle
        """
        # Get feature columns and convert them to array
        self.features_dataframe = self.dataframe.drop(columns=['target'])
        self.features_array =  np.array(self.features_dataframe)
        self.name_features = self.features_dataframe

        # Get target column 
        self.target_array = np.array(self.dataframe.target)
        
        return self.features_array, self.target_array

    def fit_lasso(self, alpha=0.003):
        """
        Fit LASSO model to data.
        """
        self.model = Lasso(alpha=alpha)
        self.model.fit(self.features_array, self.target_array)

        return self.model

    def get_used_features(self, alpha=0.006):
        """
        Get the names of the features that LASSO assigns weights
        different than 0.
        """
        self.fit_lasso(alpha=alpha)
        coeffs = self.model.coef_  
        bool_coeff = [False if coef == 0 else True for coef in coeffs]     
        self.used_features = [name for name, nonzero in zip(self.name_features, bool_coeff) if nonzero]
        self.coeffs_used_features = {name : coeff for name in self.used_features for coeff in [coeff for coeff in coeffs if coeff != 0]}

        print(self.coeffs_used_features)

        return self.coeffs_used_features

    def create_dataset(self, no_numerical: int, no_categorical: int):
        """
        Takes the most important features, and creates a dataframe with just them.
        The number of numerical and categorical features can be chosen. 
        """

        # Get names of most important numerical features 
        #numerical_features = [name in self.used_features if ':' not in name]
        # if len(numerical_features) < no_numerical:
        #     self.get_used_features()
        # # If numerical features smaller than the number we want, repeat lasso with alpha 0.001 smaller 

    #def export_dataset(self):


test = DataSet('house')
test.get_used_features()

