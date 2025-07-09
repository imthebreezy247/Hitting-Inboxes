# monitor.py
class DeliverabilityMonitor:
    def __init__(self):
        self.metrics = {
            'sent': 0,
            'delivered': 0,
            'opens': 0,
            'clicks': 0,
            'bounces': 0,
            'spam_reports': 0
        }
    
    def track_engagement(self, event_type, email):
        """Track email engagement metrics"""
        self.metrics[event_type] += 1
        
        # Update subscriber engagement
        if event_type in ['opens', 'clicks']:
            subscriber_manager.update_engagement(email)
            
    def get_deliverability_score(self):
        """Calculate deliverability health score"""
        if self.metrics['sent'] == 0:
            return 0
            
        delivery_rate = self.metrics['delivered'] / self.metrics['sent']
        bounce_rate = self.metrics['bounces'] / self.metrics['sent']
        spam_rate = self.metrics['spam_reports'] / self.metrics['sent']
        
        score = (delivery_rate * 100) - (bounce_rate * 50) - (spam_rate * 200)
        return max(0, min(100, score))