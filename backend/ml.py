import datetime
import itertools
import math
import operator
import random

import numpy as np
import optuna
import pandas as pd
import plotly.express as px
from annoy import AnnoyIndex
from sklearn.metrics import accuracy_score

val_cosm = pd.read_csv('gardening_test.tsv', sep='\t')
df = val_cosm[~val_cosm['name'].isna()]

# формируем датасет с корзинами
# перевод товаров за один заказ в список
def convert_strings_to_list(x: pd.Series):
    return list(x.values)


# перевод количества товаров за один заказ в список строк
def convert_floats_to_list(x: pd.Series):
    x = x.astype(str)
    return list(x.values)


df_baskets = df.groupby('receipt_id')[['item_id', 'quantity']].agg({
    'item_id': convert_strings_to_list,
    'quantity': convert_floats_to_list
}).reset_index()
df_baskets.columns = ['receipt_id', 'basket', 'basket_count']

# создание словаря {товар: кол-во} за каждый заказ
df_baskets['element_count'] = df_baskets.apply(
    lambda x: dict(list(zip(x.basket, x.basket_count))), axis=1)

df_baskets = df_baskets.merge(
    df.drop_duplicates(subset='receipt_id'), on='receipt_id')
df_baskets = df_baskets.loc[:, [ 'receipt_id', 'basket', 'basket_count',
                                'element_count', 'local_date']]

df_element_count = df_baskets['element_count'].apply(pd.Series).fillna(0)

# соединяем с датафреймом корзин
df_baskets = pd.concat([df_baskets, df_element_count], axis=1)
df_onehot_baskets = df_baskets[df_baskets.basket.explode().unique()].astype(float)
df_onehot_baskets = np.maximum(df_onehot_baskets, 0) / np.maximum(df_onehot_baskets, 1)

df_onehot_baskets = pd.concat([df_baskets[['receipt_id', 'local_date']],
                               df_onehot_baskets],axis=1)

def user_vector(userid, df_onehot_baskets, r_b=0.9, r_g=0.7, groupsize=5):
    '''
    Возвращает вектор u (user vector representation согласно https://arxiv.org/pdf/2006.00556.pdf)
    r_b - time-decayed ratio within each group
    r_g - time-decayed ratio accross groups
    см. https://github.com/HaojiHu/TIFUKNN  "A quick start to run the codes with Ta-Feng data set."
    '''

    group_vecs = []
    df_onehot_baskets_user = df_onehot_baskets[df_onehot_baskets['receipt_id'] == userid]
    df_onehot_baskets_user = df_onehot_baskets_user.sort_values(by='local_date', ascending=False)
    df_onehot_baskets_user = df_onehot_baskets_user.drop(
        ['receipt_id', 'local_date'], axis=1)
    m = math.ceil(df_onehot_baskets_user.shape[0] / groupsize)  # кол-во групп

    for group in np.array_split(df_onehot_baskets_user, m):
      for vec in group.values:
        group_vecs = []
        for vec in group.values:
          group_vecs.append(np.array(vec)* r_b)
          r_b = r_b / 2.718281
        group_vec = np.mean(group_vecs, axis=0) * r_g
        group_vecs.append(group_vec)

    u = np.mean(group_vecs, axis=0)
    return u

userids = df_onehot_baskets['receipt_id'].unique()
userids = userids[~np.isnan(userids)]

# mapping чтобы избежать ошибки слишком большого int в Annoy
map_ids = {}
map_ids_reverse = {}
for i, id in enumerate(list(userids)):
    map_ids[id] = i
    map_ids_reverse[i] = id

devices_dict = {}
for rec_id, dev_id in zip(val_cosm['receipt_id'], val_cosm['device_id']):
    devices_dict[rec_id] = dev_id

def create_users_vecs(r_b=0.1, r_g=0.6, groupsize=5):
    '''
    Возвращает наиболее часто встречающееся значение в массиве
    '''
    users_vecs = {}
    for userid in userids:
        u = user_vector(userid, df_onehot_baskets, r_b=r_b,
                        r_g=r_g, groupsize=groupsize)
        users_vecs[userid] = u

    return users_vecs


def create_annoy(users_vecs) -> dict:
    '''
    Создает векторное пространство чеков для нахождения наиболее близких пользователю чеков
    Пространство создается для каждого device_id
    '''
    f = len(random.choice(list(users_vecs.values())))  # размерность
    dev_annoys = {}  # cоздаем AnnoyIndex под каждый device_id
    for dev_id in val_cosm['device_id'].unique():
        t = AnnoyIndex(f, 'euclidean')
        for id in list(users_vecs.keys()):
            if devices_dict[id] == dev_id:
                t.add_item(map_ids[id], users_vecs[id])
        t.build(10)  # построение 10 деревьев
        dev_annoys[dev_id] = t

    return dev_annoys

def most_common(L):
    '''
    Возвращает наиболее часто встречающееся значение в массиве
    '''
    # get an iterable of (item, iterable) pairs
    SL = sorted((x, i) for i, x in enumerate(L))
    # print 'SL:', SL
    groups = itertools.groupby(SL, key=operator.itemgetter(0))
    # auxiliary function to get "quality" for an item

    def _auxfun(g):
        item, iterable = g
        count = 0
        min_index = len(L)
        for _, where in iterable:
            count += 1
            min_index = min(min_index, where)
        # print 'item %r, count %r, minind %r' % (item, count, min_index)
        return count, -min_index

    # pick the highest-count/earliest item
    try:
        return max(groups, key=_auxfun)[0]
    except Exception as e:
        return None


def popular_time_device(val_cosm):
    '''
    Возвращает самые популярные товары в каждый интервал времени суток (утро, день, вечер, ночь)
    по каждому device_id
    '''
    val_cosm['local_date'] = pd.to_datetime(val_cosm['local_date'])
    dev_popular = {}
    for dev_id in val_cosm['device_id'].unique():
        df_dev = val_cosm[val_cosm['device_id'] == dev_id]
        night, morn, day, evening = [], [], [], []

        for index, row in df_dev.iterrows():
            if datetime.time(00, 00) < row['local_date'].time() <= datetime.time(6, 00):
                night.append(row['item_id'])
            elif datetime.time(6, 00) < row['local_date'].time() <= datetime.time(12, 00):
                morn.append(row['item_id'])
            elif datetime.time(12, 00) < row['local_date'].time() <= datetime.time(18, 00):
                day.append(row['item_id'])
            elif datetime.time(18, 00) < row['local_date'].time() <= datetime.time(23, 59):
                evening.append(row['item_id'])

        dev_popular[dev_id] = most_common(night), most_common(
            morn), most_common(day), most_common(evening)
    return dev_popular

def pred_one_receipt(receipt_id:int, dev_annoys:dict, users_vecs:dict, item_ids: list, top_items:dict,
                  n=10, k=10, alpha=0.7,
                     mode='regular', focus_item=None, mode_weight=0) ->list:
    '''
    Функция возвращает NextBestOffer для каждого чека по его receipt_id
    в рамках device_id с учетом дневной сезонности.

    Входные аргументы:
    receipt_id - id чека
    dev_annoys - словарь AnnoyIndex (индексов для сравнения близости векторов предпочтений пользователей)
    users_vecs - эмбеддинги пользователей для tufu-knn
    top_items - top_items в каждое время суток для каждого device_id
    focus_item - item_id для дискриминативного\преимущественного предложения товара
    mode_weight - float принадлежащий интервалу [0, 1], параметр регулирующий вклад discriminative\preferential предложения
    item_ids - упорядоченный список id товаров
    mode:
    — regular - обычное предсказание
    — discriminative - убираем focus_item из выдачи
    — preferential - преимущественно предлагаем focus_item

    Выход:
    item_id являющийся NextBestOffer
    '''
    target_vector = users_vecs[receipt_id]
    dev_id = devices_dict[receipt_id]
    u = dev_annoys[dev_id]
    nearest_neighbors = u.get_nns_by_vector(target_vector, k)
    target_val_row = val_cosm[val_cosm['receipt_id'] == receipt_id]
    top_item_receipt = []

    if datetime.time(00, 00) < target_val_row['local_date'].mean().time() <= datetime.time(6, 00):
        top_item_receipt = top_items[dev_id][0]
    elif datetime.time(6, 00) < target_val_row['local_date'].mean().time() <= datetime.time(12, 00):
        top_item_receipt = top_items[dev_id][1]
    elif datetime.time(12, 00) < target_val_row['local_date'].mean().time() <= datetime.time(18, 00):
        top_item_receipt = top_items[dev_id][2]
    elif datetime.time(18, 00) < target_val_row['local_date'].mean().time() <= datetime.time(23, 59):
        top_item_receipt = top_items[dev_id][3]

    user_items = np.array(val_cosm[val_cosm['receipt_id'] == receipt_id]['item_id'])
    if mode=='regular':
      if top_item_receipt in user_items:
          P = alpha * target_vector + (1-alpha) \
              * np.mean([users_vecs.get(map_ids_reverse[key])
                        for key in nearest_neighbors], axis=0)
          #rec_inds = np.argpartition(P, -n)[-n:]
          rec_inds = np.argsort(P)[::-1][:n]
          #items = np.array(test_cosm['item_id'])
          rec_items = item_ids[rec_inds]
          return rec_items[0]
      else:
          return top_item_receipt
    elif mode=='discriminative':
      focus_item_ind = np.where(item_ids==focus_item)
      mode_vector = np.zeros(shape=(1, len(item_ids)))
      mode_vector[focus_item_ind] = 1
      P = (1-mode_weight) * (alpha * target_vector + (1-alpha) \
              * np.mean([users_vecs.get(map_ids_reverse[key])
                        for key in nearest_neighbors], axis=0)) \
              - mode_weight*mode_vector
      #rec_inds = np.argpartition(P, -n)[-n:]
      #items = np.array(test_cosm['item_id'])
      rec_inds = np.argsort(P)[::-1][:n]
      rec_items = item_ids[rec_inds]
      return rec_items[0]
    elif mode=='preferential':
      focus_item_ind = np.where(item_ids==focus_item)
      mode_vector = np.zeros(len(item_ids))
      mode_vector[focus_item_ind] = 1
      P = (1-mode_weight) * (alpha * target_vector + (1-alpha) \
              * np.mean([users_vecs.get(map_ids_reverse[key])
                        for key in nearest_neighbors], axis=0)) \
              + mode_weight*mode_vector
      #rec_inds = np.argpartition(P, -n)[-n:]
      rec_inds = np.argsort(P)[::-1][:n]
          #items = np.array(test_cosm['item_id'])
      rec_items = item_ids[rec_inds]
      return rec_items[0]

users_vecs = create_users_vecs()
dev_annoys = create_annoy(users_vecs)
item_ids = np.array(df_onehot_baskets.columns[2:])

top_items = popular_time_device(val_cosm)
res = [pred_one_receipt(id, dev_annoys, users_vecs, item_ids, top_items)
       for id in test_cosm['receipt_id']]