from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException, NoSuchElementException, StaleElementReferenceException, NoSuchWindowException
from unicodedata import normalize as unorm
import bs4, pickle, re
from bs4 import BeautifulSoup
import time,os
from copy import copy


def get_infile_name():
	files = os.listdir()
	for f in files:
		if m:=re.match(r"^schools_register(\d+)\.pkl$", f):
			return f

def get_outfile_name(infile_name):
	m=re.match(r"^schools_register(\d+)\.pkl$", infile_name)
	if not m:
		raise Exception(f"Unexpected input file name: {infile_name}")
	return f"schools_results{m.groups()[0]}.pkl"


BASE_URL = "https://bus.gov.ru"
REGISTER_FNAME = get_infile_name()
RESULTS_FNAME = get_outfile_name(REGISTER_FNAME)
HTML_RES_FILE = "pretty_scrape.html"

# how many times to retry fetching a URL 
# on network error
RETRIES_ON_NETERROR = 15 
# how long to wait between retries (in seconds)
NETERROR_PAUSE = 10

def load_file(fname):
	with open(fname, "rb") as f:
		regions = pickle.load(f)
	return regions


def filter_schools(schools):
	"""
	Return a list containing only those schools
	that have a 'main_url' field and remove duplicates
	"""
	unique = {}
	res = []
	for school in schools:
		if ('main_url' in school) and ('details_url' in school):
			if school['main_url'] not in unique:
				res.append(school)
				unique[school['main_url']] = True
	return res


def filter_new(reg_schools, saved_schools):
	""" 
	Return a list containing only those schools 
	that haven't been processed before
	"""
	unique_saved = {}
	for school in saved_schools:
		unique_saved[school['main_url']] = True
	res = []
	for school in reg_schools:
		if ('main_url' in school) and (school['main_url'] not in unique_saved):
			res.append(school)
	return res



def load_schools(register_fname=REGISTER_FNAME, results_fname=RESULTS_FNAME):
	schools = load_file(register_fname)

	try:
		saved_schools = load_file(results_fname)
	except FileNotFoundError:
		saved_schools = []

	ilen = len(schools)
	print (f"Loaded {ilen} records from {fname}")
	schools = filter_schools(schools)
	schools = filter_new(schools, saved_schools)
	print (f"Removed {ilen-len(schools)} records from the initially loaded list: {len(schools)} remaining.")
	return schools

def get_url(driver, surl, retries=RETRIES_ON_NETERROR, pause=NETERROR_PAUSE):
	for t in range(retries):
		try:
			driver.get(surl)
			break
		except WebDriverException:
			print ("Encountered a driver error while trying to read a page. Retrying...")
			time.sleep(pause)
			continue


def init_driver(surl=None):
	driver = webdriver.Firefox()
	if surl is not None:
		get_url(driver, surl)
	return driver



if __name__ == "__main__":
	schools = load_schools()
	print ([school['details_url'] for school in schools[:2]])
