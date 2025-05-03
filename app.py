import streamlit as st
from serpapi import GoogleSearch
import time
import pandas as pd

st.title("Ad-Spending Business Finder (GATC + CSV Export + Lookback Control)")

# Input fields
business_type = st.text_input("Business Type (e.g., HVAC, landscaper)", "")
city = st.text_input("City and State (e.g., Pasadena, CA)", "")
lookback_days = st.number_input("Only show advertisers active in the last X days:", min_value=1, max_value=365, value=30)
api_key = st.secrets["serpapi_key"]

def get_lat_lng_from_maps(city_query, api_key):
    search = GoogleSearch({
        "engine": "google_maps",
        "type": "search",
        "q": city_query,
        "api_key": api_key
    })
    result = search.get_dict()
    if "local_results" in result and result["local_results"]:
        coords = result["local_results"][0].get("gps_coordinates")
        if coords:
            lat = coords.get("latitude")
            lng = coords.get("longitude")
            return f"@{lat},{lng},14z"
    return None

if business_type and city:
    st.info("Getting location coordinates...")

    ll_value = get_lat_lng_from_maps(city, api_key)

    fallback_ll = {
        "pasadena, ca": "@34.1478,-118.1445,14z",
        "los angeles, ca": "@34.0522,-118.2437,14z",
        "san diego, ca": "@32.7157,-117.1611,14z"
    }
    if not ll_value:
        key = city.strip().lower()
        ll_value = fallback_ll.get(key)
        if ll_value:
            st.warning("Falling back to default coordinates for this city.")
        else:
            st.error("Could not determine location coordinates. Try a more specific or nearby city.")

    if ll_value:
        st.success(f"Coordinates used: {ll_value}")
        st.info("Scraping Google Maps...")

        query = f"{business_type} in {city}"
        all_results = []
        page = 0
        has_next = True

        while has_next:
            st.write(f"Scraping page {page + 1}...")

            params = {
                "engine": "google_maps",
                "type": "search",
                "q": query,
                "api_key": api_key,
                "start": page * 20,
                "ll": ll_value
            }

            search = GoogleSearch(params)
            results = search.get_dict()
            local_results = results.get("local_results", [])

            st.write(f"Found {len(local_results)} results on page {page + 1}")
            if not local_results:
                break

            all_results.extend(local_results)
            page += 1
            has_next = "serpapi_pagination" in results

            time.sleep(1.5)

        st.write(f"**Total businesses scraped:** {len(all_results)}")

        with_websites = [b for b in all_results if "website" in b]
        st.write(f"**Businesses with websites:** {len(with_websites)}")

        seen = set()
        unique_websites = []
        for b in with_websites:
            domain = b["website"].replace("https://", "").replace("http://", "").split("/")[0]
            if domain not in seen:
                seen.add(domain)
                unique_websites.append(b)

        st.write(f"**Unique websites to check for ads:** {len(unique_websites)}")

        advertised = []
        cutoff_timestamp = int(time.time()) - (lookback_days * 86400)

        for idx, biz in enumerate(unique_websites):
            domain = biz["website"].replace("https://", "").replace("http://", "").split("/")[0]
            st.write(f"Checking ads for {domain} ({idx + 1} of {len(unique_websites)})")

            ad_params = {
                "engine": "google_ads_transparency_center",
                "text": domain,
                "api_key": api_key
            }

            ad_search = GoogleSearch(ad_params)
            ad_data = ad_search.get_dict()

            st.subheader(f"Raw response for {domain}")
            st.json(ad_data)

            ad_creatives = ad_data.get("ad_creatives", [])
            recent_creatives = [a for a in ad_creatives if a.get("last_shown", 0) >= cutoff_timestamp]

            if len(recent_creatives) > 0:
                advertiser = recent_creatives[0].get("advertiser", "Unknown")
                advertiser_id = recent_creatives[0].get("advertiser_id", "N/A")
                advertised.append({
                    "name": biz.get("title"),
                    "website": biz.get("website"),
                    "domain": domain,
                    "ads_found": len(recent_creatives),
                    "advertiser": advertiser,
                    "advertiser_id": advertiser_id
                })

            time.sleep(1.5)

        st.write(f"**Advertisers with ads in the last {lookback_days} days:** {len(advertised)}")

        if advertised:
            df = pd.DataFrame(advertised)
            st.dataframe(df)

            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download results as CSV",
                data=csv,
                file_name="advertisers_recent.csv",
                mime="text/csv"
            )
        else:
            st.warning("No advertisers found in that timeframe.")
