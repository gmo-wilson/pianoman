# Piano Practice Timer (Raspberry Pi Touchscreen)

This project tracks piano practice time by reading USB MIDI, displays the remaining time on a fullscreen touch interface, and logs the sessions to a Google Sheet. 

No external hardware (buttons, LEDs, or voltmeters) is needed—everything is handled via the Raspberry Pi's touchscreen display.

## 1. Google Apps Script Setup (Backend)

We use Google Apps Script to allow the Pi to write directly to a Google Sheet.

1. Go to Google Sheets and create a new spreadsheet (e.g., "Piano Logs").
2. Click **Extensions > Apps Script**.
3. Paste the contents of `appscript/Code.gs` into the editor.
4. Click **Deploy > New deployment**, select type **Web app**.
5. Set "Execute as" to **Me** and "Who has access" to **Anyone**.
6. Click **Deploy** and authorize the permissions.
7. **Copy the "Web app URL"** and paste it into `pi/piano_timer.py`.

---

## 2. Hardware Setup

1. Connect your **Raspberry Pi 4** to a touchscreen display (like the official 7" Pi Touch Display or any HDMI touchscreen).
2. Connect a USB cable directly from the piano's USB port to one of the USB ports on the Raspberry Pi.

---

## 3. Software Setup

1. **Install Dependencies:**
Open a terminal on your Pi and install the required Python libraries. We are using `tkinter` for the user interface, which is built into Python but might require a system package to run on Linux.
```bash
sudo apt update
sudo apt install python3-tk python3-pip libasound2-dev
pip3 install mido python-rtmidi requests
```
*(Note: If you are on the newest Raspberry Pi OS "Bookworm", you may need to use a virtual environment or add `--break-system-packages` to the pip install command).*

2. **Run the Script:**
Navigate to the folder and run the script:
```bash
python3 pi/piano_timer.py
```
The app will launch in **fullscreen mode**. You can exit it by tapping the small "Exit App" button in the bottom right corner of the select screen, or by plugging in a keyboard and pressing `Escape`.

## 4. Run on Boot (Kiosk Mode)
To make the Pi start this GUI automatically when it boots up, you can configure it to autostart the script:

1. Create a service file (or edit your LXDE autostart file, depending on your OS). The easiest way on Raspberry Pi OS with a desktop is to edit the autostart file:
```bash
nano ~/.config/lxsession/LXDE-pi/autostart
```
2. Add this line to the bottom:
```bash
@/usr/bin/python3 /home/pi/path/to/Piano_timer/pi/piano_timer.py
```
