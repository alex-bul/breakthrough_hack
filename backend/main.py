import random

import uvicorn
import json

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from models import Product
from typing import List, Annotated

app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"],
                   allow_headers=["*"])

products = []
with open('products.txt', 'r', encoding='utf-8') as file:
    for i, product in enumerate(file.read().split("' , '")):
        products.append(Product(name=product.strip("'"), id=i))


@app.get("/search", description="Поиск по продуктам")
def search(q: str) -> List[Product]:
    return list(filter(lambda x: x.name.lower().startswith(q.lower()), products))[:5]


@app.post("/best_offer", description="Выдает next best offer")
def best_offer(cart: List[Product]) -> Product:
    print(cart)
    return random.choice(products)


if __name__ == '__main__':
    uvicorn.run(app, port=3030)
