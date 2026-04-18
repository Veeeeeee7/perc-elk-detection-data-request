from tkinter import *
from tkinter import ttk

import os
from argparse import Namespace
from dotenv import load_dotenv, set_key

import threading

import export_data

bg_color = "#F2EFE9"
heading_color = "#1A1A1A"
body_text_color = "#555555"
missing_field_val_color = "#FCCDCD"
regular_field_val_color = "#FFFFFF"

downloading = False

# Main Downloading Page Logic

if __name__ == "__main__":

    root = Tk()
    load_dotenv(override=True)

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

    form_entries = [Entry(form_frame, bg=regular_field_val_color), Entry(form_frame, bg=regular_field_val_color), Entry(form_frame, bg=regular_field_val_color), Entry(form_frame, bg=regular_field_val_color), Entry(form_frame, bg=regular_field_val_color), Entry(form_frame, bg=regular_field_val_color)]
    env_vals = [os.getenv("CLOUD_SQL_INSTANCE", "Not Set"), os.getenv("CLOUD_SQL_DB_NAME", "Not Set"), os.getenv("DB_USER", "Not Set"), os.getenv("DB_PASSWORD", "Not Set"), os.getenv("key_path", "Not Set"), os.getenv("output_path", "Not Set")]

    for i in range(0,6):
        form_entries[i].grid(row=i,column=1)
        if env_vals[i] != "" and env_vals[i] !="Not Set":
            form_entries[i].insert(0, env_vals[i])

    form_entry7 = Checkbutton(form_frame, text="Skip already downloaded images", fg=body_text_color, bg=bg_color, font=("Arial", 14), variable=skip_existing)
    form_entry7.grid(row=6, column=0, columnspan=2)

    #Submission

    progress_bar = ttk.Progressbar(root, orient="horizontal", length=230, mode="determinate")

    def s_check():
        entry_flagged = False
        for i in range(6):
            if form_entries[i].get() == "":
                form_entries[i].config(bg=missing_field_val_color)
                entry_flagged=True
            else:
                form_entries[i].config(bg=regular_field_val_color)
        
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

        submit_request.config(state="disabled")
        threading.Thread(target=run_export, args=(args,), daemon=True).start()

    def good_request():
        set_key(".env", "CLOUD_SQL_INSTANCE", form_entries[0].get())
        set_key(".env", "CLOUD_SQL_DB_NAME", form_entries[1].get())
        set_key(".env", "DB_USER", form_entries[2].get())
        set_key(".env", "DB_PASSWORD", form_entries[3].get())
        set_key(".env", "key_path", form_entries[4].get())
        set_key(".env", "output_path", form_entries[5].get())

    def downloading_progess(percent_complete):
        global downloading
        if not downloading and percent_complete != 0:
            progress_bar.place(x=285,y=390)
            downloading = True
        progress_bar['value']=percent_complete
        root.update_idletasks()

    submit_request = Button(root, text="Download Data", width=25, command=s_check, fg=body_text_color, font=("Arial", 14), bg=bg_color)

    def run_export(args):
        global downloading
        try:
            export_data.main(args=args, callback=downloading_progess)
        except Exception as e:
            downloading = False
            print(f"Error: {e}")
        finally:
            downloading = False
            good_request()
            root.after(0, lambda: progress_bar.place_forget())
            root.after(0, lambda: submit_request.config(state="normal"))

    header.pack(pady=(20,10))
    description.pack(pady=10)
    form_title.pack(pady=10)
    form_frame.pack()
    submit_request.pack(pady=10)

    root.update()

    root.mainloop()


# Data Analysis Logic

"""
What do I want?
It needs to be locked if the save location value is not in the .env file
It needs to be able to let the user select which file they want to view
It will Map all the data to a real map and give options for the user to look at the images at all the pinned locations
It will also have an option that allows the user to scroll through time, which removes and displays pins as are relevant to the time
this timeline feature will also allow for a heatmap prediction of where the heatmap describes the elk herde concentrations in different locations
"""

