import yfinance as yf
import datetime
import pandas as pd
import numpy as np
from finta import TA
import matplotlib.pyplot as plt

from sklearn import svm
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, VotingClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.metrics import confusion_matrix, classification_report, mean_squared_error, accuracy_score

NUM_DAYS = 1000     # The number of days of historical data to retrieve
INTERVAL = '1d'     # Sample rate of historical data
symbol = 'aapl'     # Symbol of the desired stock

# List of symbols for technical indicators
INDICATORS = ['RSI', 'MACD', 'STOCH','ADL', 'ATR', 'MOM', 'MFI', 'ROC', 'OBV', 'EMV', 'VORTEX','CCI']

start = (datetime.date.today() - datetime.timedelta( NUM_DAYS ) )
end = datetime.datetime.today()

data = yf.download(symbol, start=start, end=end, interval=INTERVAL)
data.rename(columns={"Close": 'close', "High": 'high', "Low": 'low', 'Volume': 'volume', 'Open': 'open'}, inplace=True)
#print((data.head()))

tmp = data.iloc[-60:]
tmp['close'].plot()


def _exponential_smooth(data, alpha):
    """
    Function that exponentially smooths dataset so values are less 'rigid'
    :param alpha: weight factor to weight recent values more
    """

    return data.ewm(alpha=alpha).mean()


data = _exponential_smooth(data, 0.65)

tmp1 = data.iloc[-60:]
tmp1['close'].plot()


def _get_indicator_data(data):

    for indicator in INDICATORS:
        ind_data = eval('TA.' + indicator + '(data)')
        if not isinstance(ind_data, pd.DataFrame):
            ind_data = ind_data.to_frame()
        data = data.merge(ind_data, left_index=True, right_index=True)
    data.rename(columns={"14 period EMV.": '14 period EMV'}, inplace=True)

    # Also calculate moving averages for features
    data['ema50'] = data['close'] / data['close'].ewm(50).mean()
    data['ema21'] = data['close'] / data['close'].ewm(21).mean()
    data['ema15'] = data['close'] / data['close'].ewm(14).mean()
    data['ema5'] = data['close'] / data['close'].ewm(5).mean()

    # Instead of using the actual volume value (which changes over time), we normalize it with a moving volume average
    data['normVol'] = data['volume'] / data['volume'].ewm(5).mean()

    # Remove columns that won't be used as features
    del (data['open'])
    del (data['high'])
    del (data['low'])
    del (data['volume'])
    del (data['Adj Close'])

    return data


data = _get_indicator_data(data)
#print(data.columns)
live_pred_data = data.iloc[-16:-11]
#print(live_pred_data)


def _produce_prediction(data, window):

    prediction = (data.shift(-window)['close'] >= data['close'])
    prediction = prediction.iloc[:-window]
    data['pred'] = prediction.astype(int)

    return data
data = _produce_prediction(data, window=15)

del (data['close'])
data = data.dropna()  # Some indicators produce NaN values for the first few rows, we just remove them here
data.tail()
#print((data.tail()))


def cross_Validation(data):
    # Split data into equal partitions of size len_train

    num_train = 15  # Increment of how many starting points (len(data) / num_train  =  number of train-test sets)
    len_train = 40  # Length of each train-test set

    rf_RESULTS = []
    knn_RESULTS = []
    gbt_RESULTS = []
    ensemble_RESULTS = []

    i = 0

    rf = RandomForestClassifier()
    knn = KNeighborsClassifier()

    estimators = [('knn', knn), ('rf', rf)]
    ensemble = VotingClassifier(estimators, voting='soft')

    while True:

        df = data.iloc[i * num_train: (i * num_train) + len_train]
        i += 1

        if len(df) < 40:
            break

        y = df['pred']
        features = [x for x in df.columns if x not in ['pred']]
        X = df[features]

        X_train, X_test, y_train, y_test = train_test_split(X, y, train_size=7 * len(X) // 10, shuffle=False)

        rf.fit(X_train, y_train)
        knn.fit(X_train, y_train)
        ensemble.fit(X_train, y_train)

        rf_prediction = rf.predict(X_test)
        knn_prediction = knn.predict(X_test)
        ensemble_prediction = ensemble.predict(X_test)

        rf_accuracy = accuracy_score(y_test.values, rf_prediction)
        knn_accuracy = accuracy_score(y_test.values, knn_prediction)
        ensemble_accuracy = accuracy_score(y_test.values, ensemble_prediction)

        rf_RESULTS.append(rf_accuracy)
        knn_RESULTS.append(knn_accuracy)
        ensemble_RESULTS.append(ensemble_accuracy)

    # Train random forest
    def _train_random_forest(X_train, y_train, X_test, y_test):
        """
        Function that uses random forest classifier to train the model
        :return:
        """

        # Create a new random forest classifier
        rf = RandomForestClassifier()

        # Dictionary of all values we want to test for n_estimators
        params_rf = {'n_estimators': [110, 130, 140, 150, 160, 180, 200]}

        # Use gridsearch to test all values for n_estimators
        rf_gs = GridSearchCV(rf, params_rf, cv=5)

        # Fit model to training data
        rf_gs.fit(X_train, y_train)

        # Save best model
        rf_best = rf_gs.best_estimator_

        # Check best n_estimators value
        print(rf_gs.best_params_)

        prediction = rf_best.predict(X_test)

        print(classification_report(y_test, prediction))
        print(confusion_matrix(y_test, prediction))

        return rf_best

    rf_model = _train_random_forest(X_train, y_train, X_test, y_test)

    #KNN
    def _train_KNN(X_train, y_train, X_test, y_test):

        knn = KNeighborsClassifier()
        # Create a dictionary of all values we want to test for n_neighbors
        params_knn = {'n_neighbors': np.arange(1, 20)}

        # Use gridsearch to test all values for n_neighbors
        knn_gs = GridSearchCV(knn, params_knn, cv=5)

        # Fit model to training data
        knn_gs.fit(X_train, y_train)

        # Save best model
        knn_best = knn_gs.best_estimator_

        # Check best n_neigbors value
        print(knn_gs.best_params_)

        prediction = knn_best.predict(X_test)

        print(classification_report(y_test, prediction))
        print(confusion_matrix(y_test, prediction))

        return knn_best

    knn_model = _train_KNN(X_train, y_train, X_test, y_test)
    #print(knn_model)

    def _ensemble_model(rf_model, knn_model, X_train, y_train, X_test, y_test):

        # Create a dictionary of our models
        estimators = [('knn', knn_model), ('rf', rf_model)]

        # Create our voting classifier, inputting our models
        ensemble = VotingClassifier(estimators, voting='hard')

        # fit model to training data
        ensemble.fit(X_train, y_train)

        # test our model on the test data
        print(ensemble.score(X_test, y_test))

        prediction = ensemble.predict(X_test)

        print(classification_report(y_test, prediction))
        print(confusion_matrix(y_test, prediction))

        return ensemble

    ensemble_model = _ensemble_model(rf_model, knn_model, X_train, y_train, X_test, y_test)
    #print(ensemble_model)
    live_pred_data.head()
    print(live_pred_data.head())

    print('RF Accuracy = ' + str(sum(rf_RESULTS) / len(rf_RESULTS)))
    print('KNN Accuracy = ' + str(sum(knn_RESULTS) / len(knn_RESULTS)))
    print('ENSEMBLE Accuracy = ' + str(sum(ensemble_RESULTS) / len(ensemble_RESULTS)))

    del (live_pred_data['close'])
    prediction = ensemble_model.predict(live_pred_data)
    print(prediction)


cross_Validation(data)
