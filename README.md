# Review Scraper

## Overview
This script enables scraping product reviews from **G2**, **Capterra**, and **Trustpilot** for a specific company within a given date range. The extracted reviews are saved as a JSON file, containing structured information such as the review title, description, date, reviewer name, and rating.

## Features
- **G2 Reviews:** Extract reviews, handling pagination efficiently.
- **Capterra Reviews:** Fetch reviews for the specified company and date range.
- **Trustpilot Reviews:** Retrieve reviews, including pagination and date filtering.
- **Customizable Date Range:** Filter reviews based on `start_date` and `end_date`.
- **Structured Output:** Save reviews in JSON format with relevant details.

---

## Prerequisites

### Install Dependencies
1. Install Python (>=3.8).
2. Install necessary Python libraries:
   ```bash
   pip install selenium beautifulsoup4 requests
   ```
3. Download and install the [ChromeDriver](https://chromedriver.chromium.org/downloads) compatible with your version of Chrome.
4. Add the ChromeDriver executable to your PATH.

---

## Setup

1. Clone the repository:
   ```bash
   git clone 
   cd review_scraper
   ```

2. Ensure `ChromeDriver` is properly installed and configured.

3. Verify all required Python dependencies are installed.

---

## Usage

### Running the Script
Run the script by providing the required inputs:

```bash
python scraper.py
```

### Inputs:
- **Source:** Choose from `g2`, `capterra`, or `trustpilot`.
- **Company Name:** Enter the company name to search for.
- **Start Date:** Enter the start date in the format `YYYY-MM-DD`.
- **End Date:** Enter the end date in the format `YYYY-MM-DD`.

### Example Execution for g2 and capterra
```bash
Enter source (g2/capterra/trustpilot): g2
Enter company name (e.g., zoom): zoom
Enter start date (YYYY-MM-DD): 2023-01-01
Enter end date (YYYY-MM-DD): 2023-12-31
```
### Example Exucation for trustpilot
```bash
Enter company name: zoom.us(url of the company)
```

### Output
The script generates a JSON file containing the reviews:
```
<source>_reviews.json
```
Example:
```json
[
  {
    "title": "Great tool for collaboration",
    "description": "The features are seamless and intuitive.",
    "date": "2023-01-15",
    "reviewer_name": "John Doe",
    "rating": "5 out of 5"
  }
]
```

---

## Known Limitations
1. **CAPTCHA Handling:** If CAPTCHA appears during scraping, manual intervention is required.
2. **Dynamic Website Changes:** The structure of G2, Capterra, or Trustpilot might change, requiring updates to the scraping logic.

---

## Future Enhancements
- **CAPTCHA Bypass:** Integrate CAPTCHA solving services like 2Captcha.
- **Additional Sources:** Extend functionality to include more SaaS review platforms.
- **Error Handling:** Improve exception handling for better reliability.

---

