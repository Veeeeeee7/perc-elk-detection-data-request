from tkinter import *
from argparse import Namespace
import export_data

bg_color = "#F2EFE9"
heading_color = "#1A1A1A"
body_text_color = "#555555"
missing_val_color = "#FCCDCD" 

root = Tk()
root.tk.call('tk', 'windowingsystem')
root.configure(bg=bg_color)

root.geometry("800x500")
root.title("PERC Landowner Science Data Exporter Tool")
skip_existing = BooleanVar(value=False)

# Visuals

header = Label(root, text="PERC Landowner Science Data Exporter Tool", fg=heading_color, bg=bg_color, font=("Georgia", 28, "bold"))
description = Label(root, text="Add the credentials into the text fields and a desired output folder to download the data to your device.", fg=body_text_color, bg=bg_color, font=("Arial", 14))

# Form 

form_frame = Frame(root, padx=20, pady=20, bg=bg_color)

form_title = Label(root, text="Fields", fg=heading_color, bg=bg_color, font=("Georgia", 16, "bold"))
form_label1 = Label(form_frame, text="CLOUD_SQL_INSTANCE:", fg=body_text_color, bg=bg_color, font=("Arial", 14)).grid(row=0,column=0)
form_label2 = Label(form_frame, text="CLOUD_SQL_DB_NAME:", fg=body_text_color, bg=bg_color, font=("Arial", 14)).grid(row=1,column=0)
form_label3 = Label(form_frame, text="DB_USER:", fg=body_text_color, bg=bg_color, font=("Arial", 14)).grid(row=2,column=0)
form_label4 = Label(form_frame, text="DB_PASSWORD:", fg=body_text_color, bg=bg_color, font=("Arial", 14)).grid(row=3,column=0)
form_label5 = Label(form_frame, text="path/to/service-account-key.json:", fg=body_text_color, bg=bg_color, font=("Arial", 14)).grid(row=4,column=0)
form_label6 = Label(form_frame, text="Output Folder:", fg=body_text_color, bg=bg_color, font=("Arial", 14)).grid(row=5,column=0)

form_entries = [Entry(form_frame), Entry(form_frame), Entry(form_frame), Entry(form_frame), Entry(form_frame), Entry(form_frame)] 
for i in range(0,6):
    form_entries[i].grid(row=i,column=1)

form_entry7 = Checkbutton(form_frame, text="Skip already downloaded images", fg=body_text_color, bg=bg_color, font=("Arial", 14), variable=skip_existing)
form_entry7.grid(row=6, column=0, columnspan=2)

def s_check():
    entry_flagged = False
    for i in range(6):
        if form_entries[i].get() == "":
            form_entries[i].config(bg=missing_val_color)
            entry_flagged=True
        else:
            form_entries[i].config(bg="systemTextBackgroundColor")
        
    if entry_flagged:
        return
        
    args = Namespace(
        key=form_entries[4].get(),
        output_folder=form_entries[5].get(),
        instance=form_entries[0].get(),
        db_name=form_entries[1].get(),
        db_user=form_entries[2].get(),
        db_password=form_entries[3].get(),
        skip_existing=skip_existing.get()
        )
    
    export_data.main(args=args)

#Submission

submit_request = Button(root, text="Download Data", width=25, command=s_check, fg=body_text_color, font=("Arial", 14))

header.pack(pady=(20,10))
description.pack(pady=10)
form_title.pack(pady=10)
form_frame.pack()
submit_request.pack(pady=30)

root.update()

root.mainloop()