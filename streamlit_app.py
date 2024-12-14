import streamlit as st
import pandas as pd
import time
import io
import base64
from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from groq import Groq

st.title("LinkedIn Contact Info Scraper")

# User inputs
linkedin_username = st.text_input("LinkedIn Username (Email)")
linkedin_password = st.text_input("LinkedIn Password", type="password")

uploaded_file = st.file_uploader("Upload Excel file with Profile URLs", type=["xlsx"])

process_button = st.button("Process")

if process_button:
    if not linkedin_username or not linkedin_password:
        st.error("Please enter LinkedIn credentials.")
    elif not uploaded_file:
        st.error("Please upload the Excel file containing profile URLs.")
    else:
        # Read the Excel file into a DataFrame
        df = pd.read_excel(uploaded_file)
        if "profile_url" not in df.columns:
            st.error("The uploaded Excel must have a 'profile_url' column.")
        else:
            # Initialize Selenium
            st.info("Initializing browser...")
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            # Provide a path to chromedriver if needed.
            # driver = webdriver.Chrome(executable_path='path/to/chromedriver', options=chrome_options)
            driver = webdriver.Chrome(options=chrome_options)

            st.info("Logging into LinkedIn...")
            driver.get("https://www.linkedin.com/login")
            time.sleep(3)
            username_field = driver.find_element(By.ID, "username")
            password_field = driver.find_element(By.ID, "password")

            username_field.send_keys(linkedin_username)
            password_field.send_keys(linkedin_password)
            driver.find_element(By.XPATH, "//button[@type='submit']").click()
            time.sleep(5)

            # Initialize Groq client using API key from secrets
            groq_client = Groq(api_key=st.secrets["groq"]["api_key"])

            extracted_data = []
            progress_bar = st.progress(0)
            total = len(df)
            
            for i, row in df.iterrows():
                profile_url = row['profile_url'].strip()
                if not profile_url.endswith('/'):
                    profile_url += '/'
                contact_info_url = profile_url + "overlay/contact-info/"
                
                # Load profile contact overlay
                driver.get(contact_info_url)
                time.sleep(5)  # wait for overlay
                
                # Take a screenshot
                screenshot_data = driver.get_screenshot_as_png()
                image = Image.open(io.BytesIO(screenshot_data))
                
                # Convert image to base64
                buffered = io.BytesIO()
                image.save(buffered, format="PNG")
                img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
                
                # Query Groq model
                messages = [
                    {"role": "user", 
                     "content": "Extract the phone number, email, website, and other contact info from the given LinkedIn contact-info overlay image."},
                    {"role": "system", "name":"image", "content": img_str}
                ]

                completion = groq_client.chat.completions.create(
                    model="llama-3.2-90b-vision-preview",
                    messages=messages,
                    temperature=1,
                    max_tokens=1024,
                    top_p=1,
                    stream=False,
                    stop=None,
                )
                
                extracted_text = completion.choices[0].message.content
                
                # Parse the extracted_text
                phone = ""
                email = ""
                website = ""
                other_info = ""
                
                lines = extracted_text.split('\n')
                for l in lines:
                    lower = l.lower()
                    if "phone" in lower and ":" in l:
                        phone = l.split(":",1)[1].strip()
                    elif "email" in lower and ":" in l:
                        email = l.split(":",1)[1].strip()
                    elif "website" in lower and ":" in l:
                        website = l.split(":",1)[1].strip()
                    else:
                        # Accumulate other lines as other info if they don't match
                        # a known pattern
                        other_info += l.strip() + " "
                
                extracted_data.append({
                    "profile_url": profile_url,
                    "phone": phone,
                    "email": email,
                    "website": website,
                    "other_info": other_info.strip()
                })
                
                progress_bar.progress((i+1)/total)

            driver.quit()

            # Show results
            result_df = pd.DataFrame(extracted_data)
            st.write("Extraction Results:")
            st.dataframe(result_df)

            # Provide download link
            towrite = io.BytesIO()
            result_df.to_excel(towrite, index=False, engine='openpyxl')
            towrite.seek(0)
            b64 = base64.b64encode(towrite.read()).decode()
            download_link = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="linkedin_extracted_contact_info.xlsx">Download Excel File</a>'
            st.markdown(download_link, unsafe_allow_html=True)
