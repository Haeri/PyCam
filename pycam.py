#!/usr/bin/python

import cv2, time, os, threading, sys
import numpy as np
import tkinter as tk
from PIL import Image, ImageTk, ImageEnhance
from datetime import datetime

DIMENSIONS = {
	"1440p (16:9)": (2560, 1440),
	"1080p (16:9)": (1920, 1080),
	"720p (16:9)":  (1280, 720),
	"480p (16:9)":  (853,  480),
	"480p (4:3)":  	(640,  480),
	"360p (16:9)":  (640,  360),
	"360p (4:3)":  	(480,  360),
	"240p (16:9)":  (426,  240),
	"240p (4:3)":  	(320,  240),
}

FRAMERATES = {
	"120": 120,
	"60": 60,
	"59.94": 59.94,
	"50": 50,
	"30": 30,
	"29.97": 29.97,
	"25": 25,
	"24": 24,
	"23.98": 23.98,
	"20": 20,
	"12": 12,
	"10": 10,
}

CAMERA_PORT = 0
VIDEO_EXTENSION = "avi"
IMAGE_EXTENSION = "png"
APP_NAME = "PyCam v1"
VIDEO_FOLDER = "videos"
PHOTO_FOLDER = "photos"
WINDOW_WIDTH = 600
WINDOW_HEIGHT = 500
INITIAL_RESOLUTION = "480p (16:9)"
INITIAL_FPS = "30"

class PyCam():
	def __init__(self, master, windowed = False):
		self.master = master

		self.dimensions = DIMENSIONS[INITIAL_RESOLUTION]
		self.target_fps = FRAMERATES[INITIAL_FPS]

		self.time_accm = 0
		self.frame_cnt = 0
		self.current_fps = 0
		self.start_time = 0
		self.current_ms = 0
		self.target_ms = 0
		self.record_time = 0

		self.frame_dropped = False
		self.recording = False
		self.closing = False

		self.font_size = 10
		self.font = "Verdana"

		self.in_stream = cv2.VideoCapture(CAMERA_PORT, cv2.CAP_DSHOW)		
		self.out_stream = None
		self.frame = None
		self.fourcc = cv2.VideoWriter_fourcc(*'XVID')
		
		if(windowed):
			self.master.geometry(str(WINDOW_WIDTH)+"x"+str(WINDOW_HEIGHT))
			self.viewport = (WINDOW_WIDTH, WINDOW_HEIGHT)
		else:
			self.master.attributes("-fullscreen", True)
			self.viewport = (self.master.winfo_screenwidth(), self.master.winfo_screenheight())


		# GUI
		self.canvas = tk.Canvas(self.master, width=self.viewport[0], height=self.viewport[1])
		self.canvas.place(x=0, y=0)

		self.video = self.canvas.create_image(0, 0, anchor=tk.NW)

		self.delta_ms_ui = self.canvas.create_text((10,5), anchor=tk.NW, font=(self.font, self.font_size), text="", fill="#95afc0")
		self.target_ms_ui = self.canvas.create_text((10,20), anchor=tk.NW, font=(self.font, self.font_size), text="", fill="#95afc0")
		self.settings_ui = self.canvas.create_text((10,35), anchor=tk.NW, font=(self.font, self.font_size), text=str(self.dimensions[0]) + "x" + str(self.dimensions[1]) + " " + str(self.target_fps)+"fps", fill="#95afc0")
		
		self.record_bg = self.canvas.create_rectangle((0, 0), 0, 0, fill="black")
		self.record_indicator= self.create_circle(self.viewport[0] - 20, 15, 5, "#eb4d4b")
		self.record_timer = self.canvas.create_text((self.viewport[0] - 35 , 7), anchor=tk.NE, font=(self.font, self.font_size), text="", fill="#eb4d4b")
		self.canvas.itemconfig(self.record_indicator, state='hidden')
		self.canvas.itemconfig(self.record_timer, state='hidden')
		self.canvas.itemconfig(self.record_bg, state='hidden')

		self.bottom_frame = tk.Frame(self.master, background="black")

		self.rec_btn = tk.Button(self.bottom_frame, text="REC", command=self.toggle_rec, bg="#eb4d4b", fg="white", relief=tk.FLAT, padx=10, pady=6, font=(self.font, self.font_size))
		self.rec_btn.pack(side="left")

		self.pic_btn = tk.Button(self.bottom_frame, text="PIC", command=self.take_pic, bg="#2980b9", fg="white", relief=tk.FLAT, padx=10, pady=6, font=(self.font, self.font_size))
		self.pic_btn.pack(side="left")

		self.vars_fps = tk.StringVar(self.master)
		self.vars_fps.set(INITIAL_FPS)

		self.vars_res = tk.StringVar(self.master)
		self.vars_res.set(INITIAL_RESOLUTION)

		self.opt_res = tk.OptionMenu(self.bottom_frame, self.vars_res, *DIMENSIONS.keys())
		self.opt_res.config(font=(self.font, self.font_size), relief=tk.FLAT, padx=10, pady=6)
		self.opt_res.pack(side="left")

		self.opt_fps = tk.OptionMenu(self.bottom_frame, self.vars_fps, *FRAMERATES.keys())
		self.opt_fps.config(font=(self.font, self.font_size), relief=tk.FLAT, padx=10, pady=6)
		self.opt_fps.pack(side="left")

		self.vars_res.trace("w", self._change_res)
		self.vars_fps.trace("w", self._change_fps)

		self.bottom_frame.pack(side="bottom")

		self.change_resolution(INITIAL_RESOLUTION)
		self.change_fps(INITIAL_FPS)


		self.cvt = threading.Thread(target=self.cv_thread)
		self.cvt.start()

		self.master.after(int(self.target_ms), self.main_loop)
			
	def main_loop(self):
		# Video Update
		if self.frame is not None :
			image = cv2.cvtColor(self.frame, cv2.COLOR_BGR2RGB)
			image = self.resize_image(image, self.viewport)
			image = Image.fromarray(image)

			# Image Filter
			#converter = ImageEnhance.Color(image)
			#image = converter.enhance(0.0)

			image = ImageTk.PhotoImage(image)

			self.canvas.itemconfig(self.video, image=image)
			self.canvas.image = image
		
		# GUI update
		drop_color = "#95afc0"
		if(self.frame_dropped):
			drop_color = "#eb4d4b"
			self.frame_dropped = False
			
		if(self.recording):
			t = datetime.fromtimestamp(self.record_time / 1000)
			self.canvas.itemconfig(self.record_timer, text=t.strftime("%H:%M:%S.%f"))
			x1, y1, x2, y2 = self.canvas.bbox(self.record_timer)
			self.canvas.coords(self.record_bg, x1, y1, x2+ 25, y2)

		self.canvas.itemconfig(self.target_ms_ui, text="TARGET:  "+str(int(self.target_ms*1000))+"MS   "+str(self.target_fps)+"FPS")
		self.canvas.itemconfig(self.delta_ms_ui, text="CURRENT: "+str(int(self.current_ms*1000))+"MS   "+str(self.current_fps)+"FPS", fill=drop_color)
		
		self.master.after(int(self.target_ms), self.main_loop)

	def create_circle(self, x, y, r, fill):
		x0 = x - r
		y0 = y - r
		x1 = x + r
		y1 = y + r
		return self.canvas.create_oval(x0, y0, x1, y1, fill=fill, outline="")

	def toggle_rec(self):
		if(self.recording):
			self.stop_rec()
		else: 
			self.start_rec()

	def take_pic(self):
		if not os.path.exists(PHOTO_FOLDER):
			os.makedirs(PHOTO_FOLDER)
		file_name = PHOTO_FOLDER + "/" + str(int(time.time())) + "." + IMAGE_EXTENSION

		print(file_name)
		cv2.imwrite(file_name, self.frame)
	
	def _change_res(self, var, index, mode):
		self.change_resolution(self.vars_res.get())

	def change_resolution(self, resolution):
		self.dimensions = DIMENSIONS[resolution]
		self.in_stream.set(cv2.CAP_PROP_FRAME_WIDTH, self.dimensions[0])
		self.in_stream.set(cv2.CAP_PROP_FRAME_HEIGHT, self.dimensions[1])
		self.dimensions = (int(self.in_stream.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self.in_stream.get(cv2.CAP_PROP_FRAME_HEIGHT)))
		
		self.canvas.itemconfig(self.settings_ui, text=str(self.dimensions[0]) + "x" + str(self.dimensions[1]) + " " + str(self.target_fps)+"FPS")

	def _change_fps(self, var, index, mode):
		self.change_fps(self.vars_fps.get())
	
	def change_fps(self, fps):
		self.target_fps = FRAMERATES[fps]
		self.target_ms = (1/self.target_fps) * 1000

		self.canvas.itemconfig(self.settings_ui, text=str(self.dimensions[0]) + "x" + str(self.dimensions[1]) + " " + str(self.target_fps)+"FPS")

	def start_rec(self):
		if not os.path.exists(VIDEO_FOLDER):
			os.makedirs(VIDEO_FOLDER)
		file_name = VIDEO_FOLDER + "/" + str(int(time.time())) + "." + VIDEO_EXTENSION
		print(file_name)
		self.out_stream = cv2.VideoWriter(file_name, self.fourcc, self.target_fps, (self.dimensions[0], self.dimensions[1]))
		self.recording = True

		# UI
		self.rec_btn.config(text="STOP", bg="gray")
		self.canvas.itemconfig(self.record_indicator, state='normal')
		self.canvas.itemconfig(self.record_timer, state='normal')
		self.canvas.itemconfig(self.record_bg, state='normal')


	def stop_rec(self):
		self.out_stream.release()
		self.out_stream = None
		self.recording = False
		self.record_time = 0

		# UI
		self.rec_btn.config(text="REC", bg="#eb4d4b")
		self.canvas.itemconfig(self.record_indicator, state='hidden')
		self.canvas.itemconfig(self.record_timer, state='hidden')
		self.canvas.itemconfig(self.record_bg, state='hidden')


	def close(self):
		self.closing = True
		self.cvt.join()

	def resize_image(self, img, size):
		h, w = img.shape[:2]
		fw, fh  = size[:2]
		a = w/h

		top = 0
		bottom = 0
		left = 0
		right = 0

		if w/h > fw/fh:
			nw = fw
			nh = int(fw/a)

			absh = abs(fh - nh)
			top = int(absh / 2)
			bottom = absh - top
		elif w/h < fw/fh:
			nw = int(fh*a)
			nh = fh

			absw = abs(fw - nw)
			left = int(absw / 2)
			right = absw - left
		else:
			nw = fw
			nh = fh

		img = cv2.resize(img, (nw, nh), cv2.INTER_LINEAR)
		img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=[0, 0, 0])

		return img
	
	def cv_thread(self):
		while not self.closing:
			# Image
			check, self.frame = self.in_stream.read()

			if(self.recording):
				self.out_stream.write(self.frame)
				self.record_time = self.record_time + self.current_ms

			# Timeing
			now = time.time()*1000
			self.current_ms = now - self.start_time
			self.start_time = now
			self.time_accm = self.time_accm + self.current_ms
			self.frame_cnt = self.frame_cnt + 1

			if self.time_accm > 1000:
				self.current_fps = self.frame_cnt
				self.time_accm = 0
				self.frame_cnt = 0
				

			if(self.current_ms < self.target_ms):
				cv2.waitKey(int(self.target_ms - self.current_ms))
			else:
				cv2.waitKey(1)
				self.frame_dropped = True

		if self.out_stream is not None:
			self.stop_rec()

		self.in_stream.release()
		cv2.destroyAllWindows()

if __name__ == "__main__":
	windowed = "-w" in sys.argv[1:]

	try:
		root = tk.Tk()
		app = PyCam(master=root, windowed=windowed)
		root.mainloop()
	finally:
		app.close()
