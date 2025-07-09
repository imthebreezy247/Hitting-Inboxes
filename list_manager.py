# list_manager.py
import csv
import json
from datetime import datetime

class SubscriberManager:
    def __init__(self, db_file='subscribers.json'):
        self.db_file = db_file
        self.load_subscribers()
        
    def load_subscribers(self):
        """Load subscriber list from file"""
        try:
            with open(self.db_file, 'r') as f:
                self.subscribers = json.load(f)
        except FileNotFoundError:
            self.subscribers = []
            
    def save_subscribers(self):
        """Save subscriber list to file"""
        with open(self.db_file, 'w') as f:
            json.dump(self.subscribers, f, indent=2)
            
    def add_subscriber(self, email, name, company=None):
        """Add new subscriber with double opt-in status"""
        subscriber = {
            'email': email,
            'name': name,
            'company': company,
            'subscribed_date': datetime.now().isoformat(),
            'status': 'active',
            'bounce_count': 0,
            'last_engaged': datetime.now().isoformat()
        }
        self.subscribers.append(subscriber)
        self.save_subscribers()
        
    def unsubscribe(self, email):
        """Mark subscriber as unsubscribed"""
        for sub in self.subscribers:
            if sub['email'] == email:
                sub['status'] = 'unsubscribed'
                sub['unsubscribed_date'] = datetime.now().isoformat()
        self.save_subscribers()
        
    def clean_list(self):
        """Remove hard bounces and inactive subscribers"""
        active_subscribers = []
        for sub in self.subscribers:
            if sub['status'] == 'active' and sub['bounce_count'] < 3:
                active_subscribers.append(sub)
        return active_subscribers