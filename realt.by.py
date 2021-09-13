import csv
import json
import traceback
import re
from urllib.parse import urljoin
from multiprocessing import Manager, Process

import requests
from bs4 import BeautifulSoup


BASE_URL = 'https://realt.by/'


class Location():
    def __init__(self, longitude=str(), latitude=str(), region=str(),
                 locality=str(), region_district=str(), direction=str(),
                 address=str()):
        self.longitude = longitude
        self.latitude = latitude
        self.region = region
        self.region_district = region_district
        self.direction = direction
        self.address = address
        self.locality = locality


class Agent():
    def __init__(self, name=str(), email=str(), phone_numbers=list()):
        self.name = name
        self.email = email
        self.phone_numbers = phone_numbers


class Product():
    def __init__(self, id=int(), url=str(), published=str(), object_type=str(),
                 title=str(), price=float(), agent=Agent(),
                 location=Location()):
        self.id = id
        self.url = url
        self.published = published
        self.title = title
        self.price = price
        self.agent = agent
        self.location = location
        self.object_type = object_type


def get_html(url, params=None):
    response = requests.get(url, params)
    if response.ok:
        return response.text


def get_product(product_url) -> Product:
    print('Start:', product_url)

    html = get_html(product_url)
    soup = BeautifulSoup(html, 'lxml')

    product = Product()
    product.location = Location()
    product.agent = Agent()
    product.agent.phone_numbers = list()
    product.id = product_url.rstrip('/').split('/')[-1]
    product.url = product_url

    if (published_string := soup.find(string=re.compile('Опубликовано'))):
        product.published = published_string[13:]

    if (title_tag := soup.find('h1', class_=['h-giant'])):
        product.title = title_tag.text.strip()

    if (price_tag := soup.find(class_='price-block')):
        product.price = price_tag.find(class_='d-flex').text.strip()

    if (agent_name_tag := soup.find(class_='agent-block')):
        product.agent.name = agent_name_tag.find('strong').text.strip()

    if (contacts_tag := soup.find(class_='object-contacts')):
        for a_tag in contacts_tag.find_all('a'):
            href = a_tag.get('href')
            if href.startswith('tel:'):
                product.agent.phone_numbers.append(href.removeprefix('tel:'))
            elif href.startswith('mailto:'):
                product.agent.email = href.removeprefix('mailto:')

    if (map_tag := soup.find(id='map')):
        data = json.loads(map_tag.div.get('data-center'))
        product.location.latitude = data['position.']['x']
        product.location.longitude = data['position.']['y']

    if (location_string := soup.find(string=re.compile('Местоположение'))):
        table_tag = location_string.parent.parent.find('table')
        for tr_tag in table_tag.find_all('tr'):
            td_tags = tr_tag.find_all('td')
            if len(td_tags) == 2:
                td_text = td_tags[0].text
                if 'Область' in td_text:
                    product.location.region = td_tags[1].text.strip()
                elif 'Населенный пункт' in td_text:
                    product.location.locality = td_tags[1].text.strip()
                elif 'Адрес' in td_text:
                    product.location.address = td_tags[1].text.strip()
                elif 'Район' in td_text:
                    product.location.region_district = td_tags[1].text.strip()
                elif 'Направление' in td_text:
                    product.location.direction = td_tags[1].text.strip()

    if (object_type_string := soup.find(string=re.compile('Вид объекта'))):
        td_tags = object_type_string.parent.parent.find_all('td')
        if len(td_tags) == 2:
            product.object_type = td_tags[1].text.strip()

    return product


def parse_products(html: str) -> list[Product]:
    soup = BeautifulSoup(html, 'lxml')
    products = []
    for item_tag in soup.find_all('div', class_=re.compile('listing-item')):
        try:
            product_url = item_tag.find(class_='desc').a.get('href')
        except Exception:
            continue
        else:
            try:
                product = get_product(product_url)
                products.append(product)
            except Exception:
                print('-----')
                print(product_url)
                traceback.print_exc()
                print('-----')

    return products


def parse_last_page_number(html: str):
    soup = BeautifulSoup(html, 'lxml')
    paging_list_tag = soup.find('div', {'class': 'paging-list'})
    last_page_tag = paging_list_tag.find_all('a')[-1]
    last_page_number = int(last_page_tag.text.strip())
    return last_page_number


def get_products(category_url, count=10) -> list[Product]:
    products = []
    html = get_html(category_url)
    last_page_number = parse_last_page_number(html)
    for page in range(1, last_page_number+1):
        params = {'page': page}
        html = get_html(category_url, params)
        new_products = parse_products(html)
        if not new_products:
            break

        products += new_products
        if len(products) >= count:
            break

    return products


def save_to_json(products, filename):
    products_list = []
    for product in products:
        product_dict = product.__dict__
        product_dict['agent'] = product_dict['agent'].__dict__
        product_dict['location'] = product_dict['location'].__dict__
        products_list.append(product_dict)

    with open(filename, 'w') as file:
        json.dump(products_list, file, ensure_ascii=False)


def save_to_csv(products: list[Product], filename):
    with open(filename, 'w', encoding='windows-1251', newline='') as csvfile:
        csvwriter = csv.writer(csvfile, delimiter=';')
        columns = ['ID объявления',
                   'Дата публикации',
                   'Название объявления',
                   'Стоимость сдачи',
                   'Имя владельца',
                   'Контактные телефоны',
                   'Контактный email',
                   'GPS координаты',
                   'Область',
                   'Населенный пункт',
                   'Район области',
                   'Направление',
                   'Адрес',
                   'Вид объекта',
                   'URL объявления']

        csvwriter.writerow(columns)
        for product in products:
            row = [product.id, product.published, product.title, product.price,
                   product.agent.name, product.agent.phone_numbers,
                   product.agent.email,
                   product.location.latitude+', '+product.location.longitude,
                   product.location.region, product.location.locality,
                   product.location.region_district,
                   product.location.direction,
                   product.location.address, product.object_type, product.url]
            csvwriter.writerow(row)


def main():
    category_url = urljoin(BASE_URL, 'rent/cottage-for-long')
    products = get_products(category_url, 10)
    save_to_csv(products, 'realt.by.csv')
    save_to_json(products, 'realt.by.json')


if __name__ == "__main__":
    main()
