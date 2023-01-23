"""
@author: Monse Guedes Ayala
@project: Poisoning Attacks Paper

This is the model building file for the models.

The PisonAttackModel is a model class, and inside that class all 
gurobipy objects, as well as a model class, are stored. It imports 
all functions from the auxiliary_functions scripts, data is given to 
the model as an input class, and lower-level variables are bounded usign 
the developed bounding procedure. 

The RegressionModel is another model class, and inside that class 
all gurobipy objects, as well as a model class, are stored. It imports 
all functions from another scripts, data is given to the model as an input 
class.

The BenchmarkPoisonAttackModel is another model class, and inside that class 
all pyomo objects are stored. It imports all functions from another script, data 
is given to the model as an input class.

"""

# Python Libraries
from os import path
import gurobipy as gp
from gurobipy import GRB
import itertools
import pyomo.environ as pyo
import pyomo.kernel as pmo

# Self-created modules
import model.auxiliary_functions as aux
import model.instance_class
import algorithm.bounding_procedure as bnd

class PoisonAttackModel():
    """
    This is the class of the model, which has
    all parameters, variables, constraints and 
    objective of the MINLP problem (using KKTs).
    """ 

    def __init__(self, m: gp.Model,  instance_data: model.instance_class.InstanceData, function='MSE' , **kwds,):  # Use initialisation parameters from AbtractModel class
        """
        m: a gurobipy empty model.
        instance_data: a class object with all data.
        function: type of objective function to be used.
        """

        super().__init__(**kwds)  # Gives access to methods in a superclass from the subclass that inherits from it
        self.model = m
        self.function = function
        self.build_parameters(instance_data)
        self.build_variables(instance_data)
        self.build_constraints()
        self.build_objective()
        self.model.update()
        
    def __repr__(self) -> str:
        return super().__repr__()

    def build_parameters(self, instance_data: model.instance_class.InstanceData):
        """
        Parameters of the single level model: 
        - number of training samples.
        - number of poisoned samples.
        - number of numerical features.
        - number of categorical features, and number of categories per feature.
        - sets for each of the above numbers.
        - data for numerical features.
        - data for categorical features. 
        - response variable of training data.
        - response variable of poisoning data.
        - regularization parameter.
        """

        print('Defining parameters')
       
        # Order of sets
        self.no_samples = instance_data.no_samples  #No. of non-poisoned samples
        self.no_psamples = instance_data.no_psamples  #No. of poisoned samples
        self.no_numfeatures = instance_data.no_numfeatures  # No. of numerical features
        self.no_catfeatures = instance_data.no_catfeatures  # No. of categorical features
        print('No. training samples is:', self.no_samples)
        print('No. poisoning samples is:', self.no_psamples)
        
        # Sets
        self.samples_set = range(1, self.no_samples + 1)   # Set of non-poisoned samples 
        self.psamples_set = range(1, self.no_psamples + 1)   # Set of poisoned samples 
        self.numfeatures_set = range(1, self.no_numfeatures + 1)   # Set of numerical features
        self.catfeatures_set = range(1, self.no_catfeatures + 1)   # Set of categorical features
        self.no_categories = instance_data.no_categories_dict   # Depends on categorical features

        # Parameters
        self.x_train_num = instance_data.num_x_train_dataframe.to_dict()
        self.x_train_cat = instance_data.cat_x_train_dataframe.to_dict()['x_train_cat']
        self.y_train = instance_data.y_train_dataframe.to_dict()['y_train']
        self.y_poison = instance_data.y_poison_dataframe.to_dict()['y_poison']
        self.regularization = instance_data.regularization

        print('Parameters have been defined')

    def build_variables(self, instance_data: model.instance_class.InstanceData):
        """
        Decision variables of single level model: 
        - poisoning samples for numerical features.
        - poisoning samples for categorical features.
        - numerical weights.
        - categorical weights. 
        - bias term.
        - auxiliary variables for triinear terms.
        - auxiliary variables for bilinear terms. 
        """

        print('Creating variables')

        # Defining bounds for lower-level variables (regression parameters)
        self.upper_bound = bnd.find_bounds(instance_data, self)
        self.lower_bound = - self.upper_bound

        self.x_poison_num = self.model.addVars(self.psamples_set, self.numfeatures_set, vtype=GRB.CONTINUOUS, lb=0, ub=1, name='x_poison_num')

        scc_indices = [(sample, cat_feature, category)    # Index of variables for categorical features
                       for sample in self.psamples_set 
                       for cat_feature in self.catfeatures_set 
                       for category in range(1, self.no_categories[cat_feature] + 1)]
        self.x_poison_cat = self.model.addVars(scc_indices, vtype=GRB.BINARY, name='x_poison_cat')
        
        self.weights_num = self.model.addVars(self.numfeatures_set, vtype=GRB.CONTINUOUS, lb=self.lower_bound, ub=self.upper_bound, name='weights_num')

        cc_indices = [(cat_feature, category)    # Index for categorical weights 
                      for cat_feature in self.catfeatures_set 
                      for category in range(1, self.no_categories[cat_feature] + 1)]
        self.weights_cat = self.model.addVars(cc_indices, vtype=GRB.CONTINUOUS, lb=self.lower_bound, ub=self.upper_bound, name='self.weights_cat')   

        self.bias = self.model.addVar(vtype=GRB.CONTINUOUS, lb=self.lower_bound, ub=self.upper_bound, name='bias')                     
        
        # Indices for trilinear terms
        sccn_indices = [(sample, cat_feature, category, num_feature)    
                         for sample in self.psamples_set
                         for num_feature in self.numfeatures_set 
                         for cat_feature in self.catfeatures_set 
                         for category in range(1, self.no_categories[cat_feature] + 1)]
        sncc_indices = [(sample, num_feature, cat_feature, category) 
                         for sample in self.psamples_set
                         for num_feature in self.numfeatures_set 
                         for cat_feature in self.catfeatures_set 
                         for category in range(1, self.no_categories[cat_feature] + 1)]
        scccc_indices = [(sample, cat_feature, category, catconstraint, categorycontraint) 
                         for sample in self.psamples_set 
                         for cat_feature in self.catfeatures_set 
                         for category in range(1, self.no_categories[cat_feature] + 1)
                         for catconstraint in self.catfeatures_set
                         for categorycontraint in range(1, self.no_categories[catconstraint] + 1)]
        # Trilinear terms
        self.tnn_ln_times_numsamples = self.model.addVars(self.psamples_set, self.numfeatures_set, self.numfeatures_set, lb=-GRB.INFINITY, ub=GRB.INFINITY)
        self.tcn_lc_times_numsamples = self.model.addVars(sccn_indices, lb=-GRB.INFINITY, ub=GRB.INFINITY)
        self.tnc_ln_times_catsamples = self.model.addVars(sncc_indices, lb=-GRB.INFINITY, ub=GRB.INFINITY)
        self.tcc_lc_times_catsample = self.model.addVars(scccc_indices, lb=-GRB.INFINITY, ub=GRB.INFINITY)
        
        # Bilinear terms
        self.ln_numweight_times_numsample = self.model.addVars(self.psamples_set, self.numfeatures_set, lb=-GRB.INFINITY, ub=GRB.INFINITY)
        self.lc_catweight_times_catsample = self.model.addVars(scc_indices, lb=-GRB.INFINITY, ub=GRB.INFINITY)
        self.zn_bias_times_numsample = self.model.addVars(self.psamples_set, self.numfeatures_set, lb=-GRB.INFINITY, ub=GRB.INFINITY)
        self.zc_bias_times_catsample = self.model.addVars(scc_indices, lb=-GRB.INFINITY, ub=GRB.INFINITY)
        
        print('Variables have been created')

    def build_constraints(self, trilinear_envelopes=False):
        """
        Constraints of the single-level reformulation: 
        - SOS 1 constraints for categorical features.
        - first order optimality conditions w.r.t. numerical weights.
        - first order optimality conditions w.r.t. categorical weights.
        - first order optimality conditions w.r.t. bias.
        - auxiliary contraints for trilinear terms.
        - auxiliary contraints for bilinear terms. 
        - optional trilinear envelopes.
        """

        print('Building contraints')
        
        print('Building SOS1 contraints')
        for psample in self.psamples_set:
            for catfeature in self.catfeatures_set:
                self.model.addConstr(aux.SOS_constraints(self, psample, catfeature) == 1, name='SOSconstraints[%s, %s]' % (psample, catfeature))

        print('Building num weights contraints')
        for numfeature in self.numfeatures_set:
            print(numfeature)
            self.model.addConstr(aux.loss_function_derivative_num_weights(self, self.function, numfeature) == 0, name='cons_first_order_optimality_conditions_num_weights[%s]' % (numfeature))

        print('Building cat weights constraints')
        for catfeature in self.catfeatures_set:
            print(catfeature)
            for category in range(1, self.no_categories[catfeature] + 1):
                print(category)
                self.model.addConstr(aux.loss_function_derivative_cat_weights(self, self.function, catfeature, category) == 0, name='cons_first_order_optimality_conditions_cat_weights[%s, %s]' % (catfeature, category))

        print('Building bias constraints')
        self.model.addConstr(aux.loss_function_derivative_bias(self) == 0, name='cons_first_order_optimality_conditions_bias')

        print('Building trilinear constraints')
        for k in self.psamples_set:
            for r in self.numfeatures_set:
                for s in self.numfeatures_set:
                    self.model.addConstr(self.ln_numweight_times_numsample[k,r] * self.x_poison_num[k,s] == self.tnn_ln_times_numsamples[k,r,s], name='cons_tnn')

        for k in self.psamples_set:
            for j in self.catfeatures_set:
                for z in range(1, self.no_categories[j] + 1):
                    for s in self.numfeatures_set:
                        self.model.addConstr(self.lc_catweight_times_catsample[k,j,z] * self.x_poison_num[k,s] == self.tcn_lc_times_numsamples[k,j,z,s], name='cons_tcn')
        
        for k in self.psamples_set:
            for r in self.numfeatures_set:
                for l in self.catfeatures_set:
                    for h in range(1, self.no_categories[l] + 1):
                        self.model.addConstr(self.ln_numweight_times_numsample[k,r] * self.x_poison_cat[k,l,h] == self.tnc_ln_times_catsamples[k,r,l,h], name='cons_tnc')
        
        for k in self.psamples_set:
            for j in self.catfeatures_set:
                for z in range(1, self.no_categories[j] + 1):
                    for l in self.catfeatures_set:
                        for h in range(1, self.no_categories[l] + 1):
                             self.model.addConstr(self.lc_catweight_times_catsample[k,j,z] * self.x_poison_cat[k,l,h] == self.tcc_lc_times_catsample[k,j,z,l,h], name='cons_tcc')
        
        print('Building bilinear constraints')
        for k in self.psamples_set:
            for r in self.numfeatures_set:
                self.model.addConstr(self.weights_num[r] * self.x_poison_num[k,r] == self.ln_numweight_times_numsample[k,r], name='cons_ln')

        for k in self.psamples_set:
            for j in self.catfeatures_set:
                for z in range(1, self.no_categories[j] + 1):
                    self.model.addConstr(self.weights_cat[j,z] * self.x_poison_cat[k,j,z] == self.lc_catweight_times_catsample[k,j,z], name='cons_lc')
        
        for k in self.psamples_set:
            for s in self.numfeatures_set:
                self.model.addConstr(self.bias * self.x_poison_num[k,s] == self.zn_bias_times_numsample[k,s], name='cons_zn')

        for k in self.psamples_set:
            for l in self.catfeatures_set:
                for h in range(1, self.no_categories[l] + 1):
                    self.model.addConstr(self.bias * self.x_poison_cat[k,l,h] == self.zc_bias_times_catsample[k,l,h], name='cons_zc')
        
        if trilinear_envelopes:
            # Trilinear envelopes 
            z = self.weights_num[r] 
            y = self.x_poison_num[k,r]
            x = self.x_poison_num[k,s]
            for k in self.psamples_set:
                for r in self.numfeatures_set:
                    for s in self.numfeatures_set:
                        # Convex
                        self.model.addConstr(self.tnn_ln_times_numsamples[k,r,s] >= self.upper_bound * self.x_poison_num[k,s] + self.upper_bound * self.x_poison_num[k,r] + self.weights_num[r] + 2 * self.lower_bound , name='convex_envelope_1')
                        self.model.addConstr(self.tnn_ln_times_numsamples[k,r,s] >= self.lower_bound * self.x_poison_num[k,s] , name='convex_envelope_2')
                        self.model.addConstr(self.tnn_ln_times_numsamples[k,r,s] >= self.lower_bound * self.x_poison_num[k,r] , name='convex_envelope_3')
                        self.model.addConstr(self.tnn_ln_times_numsamples[k,r,s] >= 1/2 * self.weights_num[r] + 1/2 * self.lower_bound , name='convex_envelope_4')
                        # Concave
                        self.model.addConstr(self.tnn_ln_times_numsamples[k,r,s] <= self.lower_bound * self.x_poison_num[k,s] + self.lower_bound * self.x_poison_num[k,r] + self.weights_num[r] + 2 * self.upper_bound , name='concave_envelope_1')
                        self.model.addConstr(self.tnn_ln_times_numsamples[k,r,s] <= self.upper_bound * self.x_poison_num[k,s] , name='concave_envelope_2')
                        self.model.addConstr(self.tnn_ln_times_numsamples[k,r,s] <= self.upper_bound * self.x_poison_num[k,r] , name='concave_envelope_3')
                        self.model.addConstr(self.tnn_ln_times_numsamples[k,r,s] <= 1/2 * self.weights_num[r] + 1/2 * self.upper_bound , name='concave_envelope_4')

        print('Constraints have been built')

    def build_objective(self):
        """
        Objective function of single-level reformulation, same as leader's 
        objective for bilevel model. Maximize the mean squared error or the 
        sum of least squares.
        """

        self.model.setObjective(aux.objective_function(self, self.function), GRB.MAXIMIZE)

        print('Objective has been built')

class RegressionModel():
    """
    This is the class of a unconstrained ridge regression model, 
    which has all parameters, variables, and objective.
    """ 

    def __init__(self, m: gp.Model,  instance_data: model.instance_class.InstanceData, function='MSE', **kwds,):  # Use initialisation parameters from AbtractModel class
        """
        m: a gurobipy empty model.
        instance_data: a class object with all data.
        function: type of objective function to be used.
        """

        super().__init__(**kwds)  # Gives access to methods in a superclass from the subclass that inherits from it
        self.model = m
        self.function = function
        self.build_parameters(instance_data)
        self.build_variables(instance_data)
        self.build_constraints()
        self.build_objective()
        self.model.update()
        
    def __repr__(self) -> str:
        return super().__repr__()

    def build_parameters(self, instance_data: model.instance_class.InstanceData):
        """
        Parameters of the single level model: 
        - number of training samples.
        - number of features.
        - sets for each of the above numbers.
        - data for features.
        - response variable of training data.
        - regularization parameter.
        """

        print('Defining parameters')
        
        # Order of sets
        self.no_samples = instance_data.no_samples  #No. of non-poisoned samples
        self.no_features = instance_data.no_features  # No. of numerical features
        
        print('No. training samples is:', self.no_samples)
        
        # Sets
        self.samples_set = range(1, self.no_samples + 1)   # Set of non-poisoned samples 
        self.features_set = range(1, self.no_features + 1)   # Set of numerical features

        # Parameters
        self.x_train = instance_data.ridge_x_train_dataframe.to_dict()
        self.y_train = instance_data.y_train_dataframe.to_dict()['y_train']
        self.regularization = instance_data.regularization

        print('Parameters have been defined')

    def build_variables(self, instance_data: model.instance_class.InstanceData):
        """
        Decision variables of single level model: 
        - weights.
        - bias term.
        """

        print('Creating variables')
        
        self.weights = self.model.addVars(self.features_set, vtype=GRB.CONTINUOUS, lb=-GRB.INFINITY, ub=GRB.INFINITY ,name='weights')
        self.bias = self.model.addVar(vtype=GRB.CONTINUOUS, lb=-GRB.INFINITY, ub=GRB.INFINITY, name='bias')

        print('Variables have been created')

    def build_constraints(self):
        """
        There are no constraints.
        """

        print('There are no constraints')

    def build_objective(self):
        """
        Objective function of ridge regression. Maximize the mean squared error or the 
        sum of least squares.
        """

        self.model.setObjective(aux.ridge_objective_function(self, self.function), GRB.MINIMIZE)

        print('Objective has been built')

class BenchmarkPoisonAttackModel(pmo.block):
    def __init__(self,  instance_data: model.instance_class.InstanceData, **kwds):
        super().__init__(**kwds)  # Gives access to methods in a superclass from the subclass that inherits from it
        # Initialize the whole abstract model whenever PoisonAttackModel is created:
        self.build_parameters(instance_data)
        self.build_variables(instance_data)
        self.build_constraints()
        self.build_objective()

    def __repr__(self) -> str:
        return super().__repr__()

    def build_parameters(self, instance_data: model.instance_class.InstanceData):
        """
        Parameters of the single level model: sets and no. elements in sets for
        features, normal samples, and poisoned samples; training features, training 
        target, poison target, and regularization parameter. 
        """
        print('Defining parameters')
        self.no_samples =  instance_data.no_samples #Number of non-poisoned samples
        self.no_psamples =  instance_data.no_psamples #Number of poisoned samples
        self.no_num_features =  instance_data.no_num_features #Number of features of feature vector
        self.no_cat_features =  instance_data.no_cat_features
        self.no_total_features =  instance_data.no_total_features

        print('No. p samples is:', self.no_psamples)
        
        self.samples_set = range(1, self.no_samples + 1) #Set of non-poisoned samples 
        self.psamples_set = range(1, self.no_psamples + 1) #Set of poisoned samples 
        self.num_features_set = range(1, self.no_num_features + 1) #Set of elements in feature vector
        self.cat_features_set = range(1, self.no_cat_features + 1)
        self.total_features_set = range(1, self.no_total_features + 1)
        
        # Parameters
        self.x_train = instance_data.processed_x_train_dataframe.to_dict()
        self.y_train = instance_data.y_train_dataframe.to_dict()['y_train']
        self.x_poison_cat = instance_data.cat_poison_dataframe.to_dict()
        self.y_poison = instance_data.y_poison_dataframe.to_dict()['y_poison']
        self.regularization = instance_data.regularization
        print('Parameters have been defined')


    def build_variables(self, instance_data: model.instance_class.InstanceData):
        """
        Decision variables of single level model: features of poisoned samples, 
        weights of regression model, and bias of regression model.
        """

        self.x_poison = pmo.variable_dict() # Numerical feature vector of poisoned samples
        for psample in self.psamples_set:
            for numfeature in  self.num_features_set:
                self.x_poison[psample,numfeature] = pmo.variable(domain=pmo.PercentFraction)

        upper_bound =  bnd.find_bounds(instance_data, self)
        lower_bound = - upper_bound
        
        self.weights = pmo.variable_dict() # Weights for numerical features
        for numfeature in self.total_features_set:
            self.weights[numfeature] = pmo.variable(domain=pmo.Reals, lb=lower_bound, ub=upper_bound, value=0)
        
        self.bias = pmo.variable(domain=pmo.Reals, lb=lower_bound, ub=upper_bound) # Bias of the linear regresion model
        print('Variables have been created')

    def build_constraints(self):
        """
        Constraints of the single-level reformulation: first order optimality conditions
        for lower-level variables: weights and bias of regression model 
        """
        
        print('Building num weights contraints')
        self.cons_first_order_optimality_conditions_num_weights = pmo.constraint_dict()  # There is one constraint per feature
        for numfeature in self.num_features_set:
            print(numfeature)
            self.cons_first_order_optimality_conditions_num_weights[numfeature] = pmo.constraint(body=aux.loss_function_derivative_num_weights(self, numfeature), rhs=0)
        
        print('Building cat weights contraints')
        self.cons_first_order_optimality_conditions_cat_weights = pmo.constraint_dict()  # There is one constraint per feature
        for numfeature in self.num_features_set:
            print(numfeature)
            self.cons_first_order_optimality_conditions_cat_weights[numfeature] = pmo.constraint(body=aux.loss_function_derivative_cat_weights(self, numfeature), rhs=0)

        print('Building bias constraints')
        self.cons_first_order_optimality_conditions_bias = pmo.constraint(body=aux.loss_function_derivative_bias(self), rhs=0)
        
        print('Constraints have been built')
        
    def build_objective(self):
        """
        Objective function of single-level reformulation, same as leader's 
        objective for bi-level model.
        """
        
        self.objective_function = pmo.objective(expr=aux.mean_squared_error(self), 
                                                sense=pyo.maximize)

        print('Objective has been built')
    
    def build_instance(self, instance_data: model.instance_class.InstanceData):
        """
        Builds a specific instance to be used when solving the model. 

        Takes as input an object of an instance class that has several dataframes
        as attributes.
        """

        # Data in dictionary format accepted by pyomo (see documentation for more info)
        data_input = {None:
            {'x_train' : instance_data.x_train_dataframe.to_dict()} |
            instance_data.y_train_dataframe.to_dict() |
            instance_data.y_poison_dataframe.to_dict() |
            {'no_samples': {None: instance_data.no_samples},
            'no_psamples': {None: instance_data.no_psamples},
            'no_features': {None: instance_data.no_features},
            'regularization': {None: instance_data.regularization}}    
            }

        # Create Data Instance
        instance = self.create_instance(data_input, name=instance_data.iteration_count)
        
        return instance