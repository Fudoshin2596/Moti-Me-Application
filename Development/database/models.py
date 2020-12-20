from collections import Counter
from sqlalchemy import Column, Integer, String
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy_utils import EmailType, PhoneNumberType
from database.database import db
import re


class QuoteDB(db.Model):
    '''Database of quotes'''
    __tablename__ = 'Quotes'

    to_sid = Column(String(500), primary_key=True)
    quote = Column(String(1000))
    author = Column(String(100))
    catagory = Column(String(100))
    from_sid = Column(String(100))
    quote_length = Column(Integer)
    num_unique_words = Column(Integer)
    rating = Column(String(50))

    def __init__(self, to_sid, quote, author, catagory, from_sid, num_unique_words, rating):
        self.to_sid = to_sid
        self.quote = quote
        self.author = author
        self.catagory = catagory
        self.from_sid = from_sid
        self.quote_length = len(self.quote)
        self.num_unique_words = self.get_unique_words()
        self.rating = rating

    def get_unique_words(self):
        quote_list = re.split('[' ', ;, \., :, \n, \t]', self.quote)
        quote_list = [x for x in quote_list if x]  # remove empty strings
        counter = Counter(quote_list)
        return len(counter)


class User(UserMixin, db.Model):
    """User account model."""

    __tablename__ = 'Users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=False)
    email = db.Column(EmailType)
    password = db.Column(
        db.String(200),
        primary_key=False,
        unique=False,
        nullable=False)

    phone_number = db.Column(PhoneNumberType())

    created_on = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=True)

    last_login = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=True)

    def set_number(self, phone_number):
        """return user number"""
        self.phone_number = phone_number

    def get_number(self):
        """return user number"""
        return self.phone_number

    def set_password(self, password):
        """Create hashed password."""
        self.password = generate_password_hash(
            password,
            method='sha256'
        )

    def check_password(self, password):
        """Check hashed password."""
        return check_password_hash(self.password, password)

    def __repr__(self):
        return '<User {}>'.format(self.name)
