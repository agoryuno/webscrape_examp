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
REGS_FILE = get_infile_name()
RESULTS_FILE = get_outfile_name(REGS_FILE)
HTML_RES_FILE = "pretty_scrape.html"

# how many times to retry fetching a URL 
# on network error
RETRIES_ON_NETERROR = 15 
# how long to wait between retries (in seconds)
NETERROR_PAUSE = 10

# how many times to retry reading the info panel
# on the page
RETRIES_INFO = 5
# how long to wait between retries (in seconds)
INFO_PAUSE = 2

def dump_soup(soup, fname = HTML_RES_FILE):
	with open(fname, "w") as f:
		f.write(soup.prettify())


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



def load_schools(fname=REGS_FILE):
	schools = load_file(fname)

	try:
		saved_schools = load_results()
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


def open_page(school_url, driver=None, base_url=BASE_URL):
	surl = f"{base_url}/{school_url}"
	if not driver:
		driver = init_driver(surl)
	else:
		get_url(driver, surl)
		
	if driver is None:
		raise Exception("Failed to initialize driver!")
	try:
		_ = WebDriverWait(driver, 60).until(
			EC.element_to_be_clickable((By.XPATH, "//div[@class='mat-tab-label-content']") ) )
	finally:
		return driver


def get_info_soup(driver):
	divs = driver.find_elements_by_xpath("//div[@class='mat-tab-label-content']")
	div = None
	for i,d in enumerate(divs):
		if d.text == "ПРОЧАЯ ИНФОРМАЦИЯ":
			div = d
			break
	if div is None:
		return None
	div.click()
	frame = WebDriverWait(driver, 10).until(
		EC.presence_of_element_located((By.XPATH, "//div[@class='mat-tab-body-wrapper']")))
	soup = BeautifulSoup(frame.get_attribute('innerHTML') , 'html.parser')
	dump_soup(soup, "info_frame.html")
	return soup


def parse_inns(soup):
	divs = soup.find_all("div")
	res = {}
	keys = {"ИНН" : "INN", "КПП" : "KPP", "ОГРН" : "OGRN"}
	g0 = "|".join(keys.keys())
	for div in divs:
		s = div.string
		if s is not None:
			s = unorm('NFKD', s).strip()
			if m:= re.match(rf"^({g0})\s+(\w+)$", s):
				res[keys[m.groups()[0]]] = m.groups()[1]
	return res


def parse_director(soup):
	divs = soup.find_all("div")
	res = {}
	for div in divs:
		s = div.string
		if s is not None:
			s = unorm('NFKD', s).strip()
			if s == "Директор":
				name = div.parent.contents[1].string
				name = unorm('NFKD', name).strip()
				res["director"] = name
	return res


def parse_authority(soup):
	divs = soup.find_all("div")
	res = {}
	for div in divs:
		s = div.string
		if s is not None:
			s = unorm('NFKD', s).strip()
			if s == "Вышестоящая организация":
				auth = div.parent.contents[1].string
				auth = unorm('NFKD', auth).strip()
				res["authority"] = auth
	return res


def parse_subsidies(soup):
	final_tab = {"year": [], "subsidy" :[]}
	tabs =soup.find_all("mat-table") 
	if len(tabs) == 0:
		return final_tab

	tab = tabs[0]
	rows = tab.find_all("mat-row")
	
	for row in rows:
		cells = row.find_all("mat-cell")

		final_tab['year'].append(unorm('NFKD', cells[0].string).strip().replace(" ", "").replace(",", "."))
		final_tab['subsidy'].append(unorm('NFKD', cells[1].string).strip().replace(" ", "").replace(",", "."))
	return {'subsidies' : final_tab}


def parse_staff(soup):
	final_tab = {'year' : [], 'employees' : [], 'mean_salary' : []}
	tabs =soup.find_all("mat-table") 
	if len(tabs) == 0:
		return final_tab
	tab = tabs[1]
	rows = tab.find_all("mat-row")
	

	for row in rows:
		cells = row.find_all("mat-cell")
		final_tab['year'].append(unorm('NFKD', cells[0].string).strip().replace(" ", "").replace(",", "."))
		final_tab['employees'].append(unorm('NFKD', cells[1].string).strip().replace(" ", "").replace(",", "."))
		final_tab['mean_salary'].append(unorm('NFKD', cells[2].string).strip().replace(" ", "").replace(",", "."))
	return {'staff' : final_tab}


def parse_info(soup):
	app = soup.find_all("app-other-information-tab")[0]
	inns = parse_inns(soup)
	director = parse_director(soup)
	res = {**inns, **director}
	auth = parse_authority(soup)
	res = {**res, **auth}
	subsidies = parse_subsidies(soup)
	res = {**res, **subsidies}
	staff = parse_staff(soup)
	res = {**res, **staff}
	return res


def dump_results(res, fname=RESULTS_FILE):
	with open(fname, "wb") as f:
		pickle.dump(res, f)


def load_results(fname=RESULTS_FILE):
	with open(fname, "rb") as f:
		results = pickle.load(f)
	return results

if __name__ == "__main__":
	schools = load_schools()

	try:
		saved_schools = load_results()
	except FileNotFoundError:
		saved_schools = []

	driver = init_driver()
	try:
		for i, school in enumerate(schools):
			print (f"Parsing record {i+1} of {len(schools)}.")
			driver = open_page(school['main_url'], driver=driver)		
			
			info = None
			for t in range(RETRIES_INFO):
				info = get_info_soup(driver)
				if info is not None:
					break
				time.sleep(INFO_PAUSE)
			if info is None:
				continue

			dump_soup(BeautifulSoup(driver.page_source, 'html.parser'))
			res = parse_info(info)
			final = {**school, **res}
			saved_schools.append(final)
			dump_results(saved_schools)
			time.sleep(2)
	except NoSuchWindowException:
		print ("Browser window crashed or was accidentally closed. Attempting to restart...")
		time.sleep(5)
		driver = init_driver()
	finally:
		driver.quit()

	