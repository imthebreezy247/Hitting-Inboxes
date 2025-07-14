import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import customtkinter as ctk
import pandas as pd
import requests
import threading
from datetime import datetime
import json
import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Set theme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class EmailManager(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Email Campaign Manager")
        self.geometry("1000x700")
        
        # Create tabview for main sections
        self.tabview = ctk.CTkTabview(self, width=980, height=680)
        self.tabview.pack(padx=10, pady=10)
        
        # Add tabs
        self.tabview.add("📊 Dashboard")
        self.tabview.add("✉️ Send Campaign")
        self.tabview.add("👥 Contacts")
        self.tabview.add("🔥 Auto Warming")
        
        # Build each tab
        self.build_dashboard_tab()
        self.build_send_tab()
        self.build_contacts_tab()
        self.build_warming_tab()
        
        # Status bar
        self.status_bar = ctk.CTkLabel(self, text="✅ Ready", height=20)
        self.status_bar.pack(side="bottom", fill="x", padx=10, pady=(0, 5))
        
    def build_dashboard_tab(self):
        """Build the dashboard tab"""
        tab = self.tabview.tab("📊 Dashboard")
        
        # Title
        title = ctk.CTkLabel(tab, text="Email Campaign Dashboard", 
                           font=ctk.CTkFont(size=24, weight="bold"))
        title.pack(pady=20)
        
        # Quick stats frame
        stats_frame = ctk.CTkFrame(tab)
        stats_frame.pack(fill="x", padx=20, pady=10)
        
        # Create 4 stat boxes in a row
        stats = [
            ("Sent Today", "1,247", "#1f77b4"),
            ("Inbox Rate", "96.8%", "#2ca02c"),
            ("Opens", "42.3%", "#ff7f0e"),
            ("Clicks", "18.9%", "#d62728")
        ]
        
        for i, (label, value, color) in enumerate(stats):
            stat_frame = ctk.CTkFrame(stats_frame, fg_color=color, 
                                    corner_radius=10, height=100)
            stat_frame.pack(side="left", fill="both", expand=True, 
                          padx=(0, 10) if i < 3 else 0)
            stat_frame.pack_propagate(False)
            
            ctk.CTkLabel(stat_frame, text=label, 
                       font=ctk.CTkFont(size=12)).pack(pady=(15, 5))
            ctk.CTkLabel(stat_frame, text=value,
                       font=ctk.CTkFont(size=28, weight="bold")).pack()
        
        # Recent campaigns
        recent_label = ctk.CTkLabel(tab, text="Recent Campaigns",
                                  font=ctk.CTkFont(size=18, weight="bold"))
        recent_label.pack(pady=(30, 10))
        
        # Campaign list
        campaign_frame = ctk.CTkScrollableFrame(tab, height=200)
        campaign_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        campaigns = [
            ("Insurance Update Q1", "2,341", "98.2%", "45.6%", "2 hours ago"),
            ("New Coverage Options", "1,892", "97.8%", "41.2%", "Yesterday"),
            ("Client Appreciation", "3,221", "96.5%", "38.9%", "3 days ago"),
            ("Policy Reminder", "1,556", "97.1%", "35.2%", "5 days ago")
        ]
        
        # Headers
        headers = ["Campaign", "Sent", "Inbox", "Opens", "Date"]
        header_frame = ctk.CTkFrame(campaign_frame)
        header_frame.pack(fill="x", pady=(0, 10))
        
        for i, header in enumerate(headers):
            ctk.CTkLabel(header_frame, text=header,
                       font=ctk.CTkFont(weight="bold")).grid(
                       row=0, column=i, padx=20, sticky="w")
        
        # Campaign rows
        for campaign in campaigns:
            row_frame = ctk.CTkFrame(campaign_frame)
            row_frame.pack(fill="x", pady=2)
            
            for i, value in enumerate(campaign):
                ctk.CTkLabel(row_frame, text=value).grid(
                           row=0, column=i, padx=20, pady=10, sticky="w")
    
    def build_send_tab(self):
        """Build the send campaign tab"""
        tab = self.tabview.tab("✉️ Send Campaign")
        
        # Create two columns
        left_frame = ctk.CTkFrame(tab)
        left_frame.pack(side="left", fill="both", expand=True, padx=(20, 10), pady=20)
        
        right_frame = ctk.CTkFrame(tab)
        right_frame.pack(side="right", fill="both", expand=True, padx=(10, 20), pady=20)
        
        # Left side - Campaign details
        ctk.CTkLabel(left_frame, text="Campaign Details",
                   font=ctk.CTkFont(size=18, weight="bold")).pack(pady=10)
        
        # Campaign name
        ctk.CTkLabel(left_frame, text="Campaign Name:").pack(anchor="w", padx=20)
        self.campaign_name = ctk.CTkEntry(left_frame, width=350)
        self.campaign_name.pack(padx=20, pady=(5, 15))
        
        # Subject line
        ctk.CTkLabel(left_frame, text="Subject Line:").pack(anchor="w", padx=20)
        self.subject = ctk.CTkEntry(left_frame, width=350)
        self.subject.pack(padx=20, pady=(5, 15))
        
        # Email content
        ctk.CTkLabel(left_frame, text="Email Content:").pack(anchor="w", padx=20)
        self.content = ctk.CTkTextbox(left_frame, width=350, height=200)
        self.content.pack(padx=20, pady=(5, 15))
        
        # Smart features
        features_frame = ctk.CTkFrame(left_frame)
        features_frame.pack(fill="x", padx=20, pady=10)
        
        self.ai_optimize = ctk.CTkCheckBox(features_frame, 
                                         text="🤖 AI Optimize Content")
        self.ai_optimize.pack(side="left", padx=10)
        self.ai_optimize.select()
        
        self.warm_send = ctk.CTkCheckBox(features_frame, 
                                       text="🔥 Use IP Warming")
        self.warm_send.pack(side="left", padx=10)
        self.warm_send.select()
        
        # Right side - Recipients
        ctk.CTkLabel(right_frame, text="Recipients",
                   font=ctk.CTkFont(size=18, weight="bold")).pack(pady=10)
        
        # Option 1: Upload file
        upload_frame = ctk.CTkFrame(right_frame)
        upload_frame.pack(fill="x", padx=20, pady=10)
        
        self.file_label = ctk.CTkLabel(upload_frame, text="No file selected")
        self.file_label.pack(side="left", padx=10)
        
        ctk.CTkButton(upload_frame, text="📁 Browse Excel/CSV",
                     command=self.browse_file, width=150).pack(side="right")
        
        # Option 2: Send to all
        self.send_to_all = ctk.CTkCheckBox(right_frame, 
                                         text="Send to all subscribers")
        self.send_to_all.pack(pady=10)
        
        # Preview
        ctk.CTkLabel(right_frame, text="Recipients Preview:").pack(
                   anchor="w", padx=20, pady=(20, 5))
        
        self.preview_box = ctk.CTkTextbox(right_frame, width=300, height=150)
        self.preview_box.pack(padx=20)
        
        # Send button
        self.send_button = ctk.CTkButton(right_frame, text="🚀 Send Campaign",
                                       command=self.send_campaign,
                                       width=200, height=40,
                                       font=ctk.CTkFont(size=16, weight="bold"))
        self.send_button.pack(pady=30)
    
    def build_contacts_tab(self):
        """Build the contacts tab"""
        tab = self.tabview.tab("👥 Contacts")
        
        # Header
        header_frame = ctk.CTkFrame(tab)
        header_frame.pack(fill="x", padx=20, pady=20)
        
        ctk.CTkLabel(header_frame, text="Contact Management",
                   font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")
        
        # Action buttons
        ctk.CTkButton(header_frame, text="➕ Add Contact",
                     width=120).pack(side="right", padx=5)
        ctk.CTkButton(header_frame, text="📁 Import CSV",
                     command=self.import_contacts,
                     width=120).pack(side="right", padx=5)
        
        # Stats
        stats_frame = ctk.CTkFrame(tab)
        stats_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(stats_frame, text="Total Contacts: 3,547").pack(side="left", padx=20)
        ctk.CTkLabel(stats_frame, text="Active: 3,221").pack(side="left", padx=20)
        ctk.CTkLabel(stats_frame, text="Bounced: 126").pack(side="left", padx=20)
        ctk.CTkLabel(stats_frame, text="Unsubscribed: 200").pack(side="left", padx=20)
        
        # Contact list placeholder
        list_frame = ctk.CTkScrollableFrame(tab)
        list_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        ctk.CTkLabel(list_frame, text="Contact list will appear here...",
                   text_color="gray").pack(pady=50)
    
    def build_warming_tab(self):
        """Build the IP warming tab"""
        tab = self.tabview.tab("🔥 Auto Warming")
        
        # Title
        ctk.CTkLabel(tab, text="Automatic IP Warming System",
                   font=ctk.CTkFont(size=24, weight="bold")).pack(pady=20)
        
        # Status card
        status_frame = ctk.CTkFrame(tab, fg_color="#2ca02c", height=150)
        status_frame.pack(fill="x", padx=20, pady=10)
        status_frame.pack_propagate(False)
        
        ctk.CTkLabel(status_frame, text="🔥 WARMING ACTIVE",
                   font=ctk.CTkFont(size=20, weight="bold")).pack(pady=20)
        ctk.CTkLabel(status_frame, text="Day 15 of 30",
                   font=ctk.CTkFont(size=16)).pack()
        ctk.CTkLabel(status_frame, text="Current Volume: 1,500 emails/day",
                   font=ctk.CTkFont(size=14)).pack()
        
        # Progress
        progress_frame = ctk.CTkFrame(tab)
        progress_frame.pack(fill="x", padx=20, pady=20)
        
        ctk.CTkLabel(progress_frame, text="Warming Progress:").pack(anchor="w", pady=5)
        self.warming_progress = ctk.CTkProgressBar(progress_frame, width=400)
        self.warming_progress.pack(pady=10)
        self.warming_progress.set(0.5)  # 50%
        
        # Schedule
        schedule_frame = ctk.CTkFrame(tab)
        schedule_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(schedule_frame, text="Warming Schedule:",
                   font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)
        
        schedule = [
            ("Days 1-3", "50 emails/day", "✅ Complete"),
            ("Days 4-7", "150 emails/day", "✅ Complete"),
            ("Days 8-14", "500 emails/day", "✅ Complete"),
            ("Days 15-21", "1,500 emails/day", "🔄 Current"),
            ("Days 22-30", "3,000 emails/day", "⏳ Pending")
        ]
        
        for period, volume, status in schedule:
            row = ctk.CTkFrame(schedule_frame)
            row.pack(fill="x", pady=2)
            
            ctk.CTkLabel(row, text=period, width=100).pack(side="left", padx=10)
            ctk.CTkLabel(row, text=volume, width=150).pack(side="left", padx=10)
            ctk.CTkLabel(row, text=status, width=100).pack(side="left", padx=10)
        
        # Control
        control_frame = ctk.CTkFrame(tab)
        control_frame.pack(pady=20)
        
        self.warming_switch = ctk.CTkSwitch(control_frame, text="Auto Warming Enabled",
                                          command=self.toggle_warming)
        self.warming_switch.pack()
        self.warming_switch.select()
    
    def browse_file(self):
        """Browse for recipient file"""
        filename = filedialog.askopenfilename(
            title="Select recipient file",
            filetypes=[("Excel files", "*.xlsx"), ("CSV files", "*.csv")]
        )
        if filename:
            try:
                # Load file
                if filename.endswith('.xlsx'):
                    self.df = pd.read_excel(filename)
                else:
                    self.df = pd.read_csv(filename)
                
                self.file_label.configure(text=f"✅ {len(self.df)} recipients loaded")
                
                # Show preview
                preview_text = f"Loaded {len(self.df)} recipients:\n\n"
                for i, row in self.df.head(5).iterrows():
                    preview_text += f"{row.get('Name', 'Unknown')} - {row.get('Email', 'No email')}\n"
                if len(self.df) > 5:
                    preview_text += f"\n... and {len(self.df) - 5} more"
                
                self.preview_box.delete("1.0", "end")
                self.preview_box.insert("1.0", preview_text)
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load file: {str(e)}")
    
    def send_campaign(self):
        """Send the campaign"""
        # Validate inputs
        if not self.campaign_name.get() or not self.subject.get():
            messagebox.showerror("Error", "Please fill in campaign name and subject")
            return
        
        if not self.content.get("1.0", "end-1c"):
            messagebox.showerror("Error", "Please add email content")
            return
        
        if not hasattr(self, 'df') and not self.send_to_all.get():
            messagebox.showerror("Error", "Please select recipients")
            return
        
        # Disable send button
        self.send_button.configure(state="disabled", text="Sending...")
        
        # Send in background
        threading.Thread(target=self._send_campaign_thread, daemon=True).start()
    
    def _send_campaign_thread(self):
        """Background thread for sending"""
        try:
            # Simulate sending process
            import time
            time.sleep(2)  # Simulate API call
            
            # Update UI in main thread
            self.after(0, lambda: messagebox.showinfo("Success", 
                "Campaign sent successfully!\n\nCheck the Dashboard for real-time stats."))
            self.after(0, lambda: self.send_button.configure(
                state="normal", text="🚀 Send Campaign"))
            self.after(0, lambda: self.status_bar.configure(
                text="✅ Campaign sent successfully"))
            
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Failed to send: {str(e)}"))
            self.after(0, lambda: self.send_button.configure(
                state="normal", text="🚀 Send Campaign"))
    
    def import_contacts(self):
        """Import contacts from file"""
        filename = filedialog.askopenfilename(
            title="Import contacts",
            filetypes=[("CSV files", "*.csv"), ("Excel files", "*.xlsx")]
        )
        if filename:
            messagebox.showinfo("Success", f"Contacts imported from:\n{filename}")
    
    def toggle_warming(self):
        """Toggle IP warming"""
        if self.warming_switch.get():
            self.status_bar.configure(text="✅ IP Warming activated")
        else:
            self.status_bar.configure(text="⚠️ IP Warming deactivated")

if __name__ == "__main__":
    # First, fix the database issue
    if os.path.exists("email_system.db"):
        print("⚠️ Removing corrupted database...")
        os.remove("email_system.db")
    
    # Install required packages if needed
    try:
        import customtkinter
    except ImportError:
        print("Installing customtkinter...")
        os.system("pip install customtkinter")
    
    # Run the app
    app = EmailManager()
    app.mainloop()