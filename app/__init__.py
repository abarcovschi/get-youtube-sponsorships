from flask import Flask
from web_config import Config

app = Flask(__name__)
app.config.from_object(Config)

from app import routes  