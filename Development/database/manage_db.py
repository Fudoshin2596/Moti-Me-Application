from database.models import QuoteDB, User
from database.database import db


class Manage_db():
    def __init__(self, quote=None, to_sid=None, author=None, catagory=None, from_sid=None, num_unique_words=None, rating=None):
        self.to_sid = to_sid
        self.quote = quote
        self.author = author
        self.catagory = catagory
        self.from_sid = from_sid
        self.num_unique_words = num_unique_words
        self.rating = rating

    def populate_db(self):
        """ add quote content to Database """
        new_quote = QuoteDB(to_sid=self.to_sid,
                            quote=self.quote,
                            author=self.author,
                            catagory=self.catagory,
                            from_sid=self.from_sid,
                            num_unique_words=self.num_unique_words,
                            rating=self.rating)
        db.session.add(new_quote)
        db.session.commit()

    def check_db(self):
        """ check if quote in Database """
        target_query = QuoteDB.query.filter_by(quote=self.quote).first()
        if target_query is None:
            return False
        else:
            return True

    def modify_db(self, from_sid, body):
        """ add features to existing quotes """
        item = QuoteDB.query.filter_by(to_sid=self.to_sid).first()
        item.from_sid = from_sid
        item.rating = body
        db.session.commit()

    def delete_from_db(self):
        """ Delete content from Database """
        pass

    def get_size(self):
        """ returns number of items in Database """
        return len(QuoteDB.query.all())

    def get_users(self, username):
        users = User.query.filter_by(name=username).first()
        recordObject = {'name': users.name, 'number': users.phone_number}
        return recordObject['number']
