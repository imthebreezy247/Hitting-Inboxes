# templates.py

def get_email_template():
    """Return optimized email template for deliverability"""
    
    html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{subject}}</title>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background-color: #f4f4f4; padding: 20px; text-align: center; }
        .content { padding: 20px; }
        .footer { background-color: #f4f4f4; padding: 20px; text-align: center; font-size: 12px; }
        .unsubscribe { color: #666; text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>CJS Insurance Solutions</h1>
        </div>
        <div class="content">
            <p>Hi {{name}},</p>
            {{content}}
            <p>Best regards,<br>Chris<br>CJS Insurance Solutions</p>
        </div>
        <div class="footer">
            <p>CJS Insurance Solutions<br>
            123 Business Ave, Brandon, FL 33511<br>
            Phone: (555) 123-4567</p>
            <p>You're receiving this because you subscribed to our newsletter.<br>
            <a href="{{unsubscribe_link}}" class="unsubscribe">Unsubscribe</a> | 
            <a href="{{preferences_link}}" class="unsubscribe">Update Preferences</a></p>
        </div>
    </div>
</body>
</html>
"""
    
    text_template = """
Hi {{name}},

{{content}}

Best regards,
Chris
CJS Insurance Solutions

---
CJS Insurance Solutions
123 Business Ave, Brandon, FL 33511
Phone: (555) 123-4567

You're receiving this because you subscribed to our newsletter.
Unsubscribe: {{unsubscribe_link}}
Update Preferences: {{preferences_link}}
"""
    
    return html_template, text_template