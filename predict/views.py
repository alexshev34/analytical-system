from django.shortcuts import render
from django.http import HttpResponse
from twocaptcha import TwoCaptcha
from bs4 import BeautifulSoup

from pytrends.request import TrendReq
from selenium import webdriver
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

import time
import requests as rq
import datetime
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib 
matplotlib.use('Agg')

def index(request):
    return render(request, 'index.html')

def predict(request):
    def clean_period(str):
        return str.split("-")[0]

    def month_name(str):
        return str.strftime("%B")

    def get_gtrends(query):
        """Загрузка данных из google trends"""
        print(f"Query: {query} is sending")

        pytrends = TrendReq()
        pytrends.build_payload([f"{query}"], cat=0, timeframe='today 5-y', geo='RU')

        df = pytrends.interest_over_time()
        df = df.reset_index().resample('MS', on='date').mean()
        df = df.drop("isPartial", axis=1).reset_index()

        df.columns = ["Период", "Значение"]
        df['Месяц'] = df['Период'].apply(month_name)

        last_month = df['Период'].to_list()[-1]

        months_for_predict_list = list()
        periods_list = list()
        values_list = list()

        # Получаем месяцы которые нужно спрогнозировать
        for i in range(3):
            months_for_predict_list.append(month_name(last_month + datetime.timedelta(days=31)))
            periods_list.append(last_month + datetime.timedelta(days=31))
            last_month += datetime.timedelta(days=31)

        for month in months_for_predict_list:
            # Список со значениями этих месяцев за последние два года
            values_from_df_list = df.query('@month == Месяц')['Значение'].to_list()[-2:]
            value = (sum(values_from_df_list) / 2) + values_from_df_list[-1]
            values_list.append(value)

        predicted_dict = {"Период":periods_list, "Значение": values_list, "Месяц": months_for_predict_list}

        predicted_df = pd.DataFrame(predicted_dict)
        new_df = pd.concat([df, predicted_df], axis=0)

        return new_df


    def driver_init():
        service = Service(executable_path=ChromeDriverManager().install())
        options = webdriver.ChromeOptions()
        #options.add_argument('headless')
        options.add_argument('window-size=1920x935')

        driver = webdriver.Chrome(service=service, chrome_options=options)
        driver.wait = WebDriverWait(driver, 5)
        return driver

    def lookup(driver, query, isProduct):

        driver.get(f"https://wordstat.yandex.ru/#!/history?words={query}")
        driver.implicitly_wait(15)
        print("Log: get query is done")
        # Авторизация Yandex Wordstat
        auth(driver)
        print("Log: Authorization is done")
        # Загрузка капчи и получение расшифровки
        try:
            captcha_src = driver.find_element(By.XPATH, "/html/body/div[7]/div/div/table/tbody/tr/td/div/form/table/tbody/tr[1]/td/img[1]").get_attribute("src")
            captcha_text = captcha_processing(captcha_src)
            time.sleep(1)
            print(f"Log: Captcha is {captcha_text}")
            # Введение расшифровки и отправка капчи
            driver.find_element(By.XPATH, "/html/body/div[7]/div/div/table/tbody/tr/td/div/form/table/tbody/tr[2]/td[1]/span/span/input").send_keys(captcha_text)
            driver.find_element(By.XPATH, "/html/body/div[7]/div/div/table/tbody/tr/td/div/form/table/tbody/tr[2]/td[2]/span/input").click()
            time.sleep(1)
        except:
            pass
        # Загрузка html-исходников для дальнейшего парсинга
        content = driver.page_source

        df = extract_data(content, query)
        return df
    
    def auth(driver):
        '''
        Функция производит авторизацию в Yandex Wordstat для переданного driver

        Arguments:
            driver (obj): Объект selenium с открытой страницей авторизации Yandex Wordstat
        Returns:
            None: функция мутирует существующий объект driver
        '''
        login = "alexshev345@yandex.ru"
        password = "Alex562035"

        driver.find_element(By.XPATH, "/html/body/form/table/tbody/tr[2]/td[2]/div/div[2]/span/span/input").send_keys(login)
        driver.find_element(By.XPATH, "/html/body/form/table/tbody/tr[2]/td[2]/div/div[3]/span/span/input").send_keys(password)
        driver.find_element(By.XPATH, "/html/body/form/table/tbody/tr[2]/td[2]/div/div[5]/span[1]/input").click()

    def captcha_processing(src):
        '''
        Функция выгружает капчу из Yandex Wordstat и отправляет её в сервис ruCAPTCHA
        Argument:
            src (string): ссылка на капчу
        Returns:
            result (string): возвращает текст разгаданной капчи
        '''
        API_KEY = "69aea7580fad254d2994a3f8ddfec60d"
        response = rq.get(src)
        # Сохранение капчи
        out = open("captcha/img.jpg", "wb")
        out.write(response.content)
        out.close()
        # Отправка запроса к rucaptcha
        solver = TwoCaptcha(API_KEY)
        result = solver.normal('captcha/img.jpg')

        return result.get("code")

    def extract_data(html, query):
        soup = BeautifulSoup(html, 'html.parser')

        dates = list()
        values = list()

        for col in soup.find_all("tbody", attrs={"class": "b-history__table-body"}):
            for row in col:
                period = row.find("td").text
                # На яндексе части от значений разделены в разные span элементы
                values_list = row.find(class_='b-history__value-td').find_all(class_='b-history__number-part')
                value = int("".join([val.text for val in values_list]))
                
                dates.append(period)
                values.append(value)

        d = {'Период': dates, 'Значение': values}
        df = pd.DataFrame(data=d)
        df['Период'] = df['Период'].apply(clean_period)
        df['Период'] = pd.to_datetime(df['Период'], dayfirst=True)
        df['Месяц'] = df['Период'].apply(month_name)

        return df

    def predict_yandex(df):
        last_month = df['Период'].to_list()[-1]
        months_for_predict_list = list()
        periods_list = list()
        values_list = list()
        percent_list = list()

        # Получаем месяцы которые нужно спрогнозировать
        for i in range(3):
            months_for_predict_list.append(month_name(last_month + datetime.timedelta(days=31)))
            periods_list.append(last_month + datetime.timedelta(days=31))
            last_month += datetime.timedelta(days=31)

        for month in months_for_predict_list:
            # Список со значениями этих месяцев за последние два года
            values_from_df_list = df.query('@month == Месяц')['Значение'].to_list()[-2:]
            value = (sum(values_from_df_list) / 2) + values_from_df_list[-1]
            values_list.append(value)

        predicted_dict = {"Период":periods_list, "Значение": values_list, "Месяц": months_for_predict_list}
        
        return predicted_dict

    query = request.GET.getlist('query', '')[0].replace("?track_id", "")
    query_type = request.GET.getlist('query_type', '')[0]

    if query_type == "1":
        query = f"Купить {query.lower()}"

    # Получение данных из Google

    df_google = get_gtrends(query).tail(6)

    fig = sns.lineplot(data=df_google, x="Месяц", y="Значение").set_title("Google Trends")
    fig.figure.savefig(f"static/img/google_plot.png")
    plt.close()

    google_path = f"img/google_plot.png"

    # Получение данных Яндекс
    driver = driver_init()
    df_yandex = lookup(driver, query, True)

    driver.quit()
    
    print(f"Log: {df_yandex.info()}")

    predicted_dict = predict_yandex(df_yandex)
    predicted_df = pd.DataFrame(predicted_dict)
    new_df = pd.concat([df_yandex, predicted_df], axis=0).tail(6)

    fig = sns.barplot(data=new_df, x="Месяц", y="Значение").set_title("Прогноз в цифрах")
    fig.figure.savefig(f"static/img/yandex_plot.png")
    plt.close()
        

    yandex_path = "img/yandex_plot.png"

    # Проценты из Яндекса

    percent_list = [0]
    last_num = 0
    for i, row in new_df.iterrows():
        if last_num == 0:
            last_num = row["Значение"]
        else:
            percent_list.append((row["Значение"] - last_num) / last_num * 100)
            last_num = row["Значение"]

    new_df["Проценты"] =  percent_list
    percents_df = new_df.tail(5)

    months = percents_df["Месяц"].to_list()
    percents = percents_df["Проценты"].to_list()
    d = [(months[i],f"{int(percents[i])}%") for i in range(len(months))]
    print(percents_df)

    return render(request, 'predict.html', context={'google_plot_path': google_path, 'yandex_plot_path': yandex_path, 'final_list': d})
