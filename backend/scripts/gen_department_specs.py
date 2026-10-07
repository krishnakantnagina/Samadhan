"""Generate the service specs, office rows and route chains for every department in the routing registry.

    cd backend && uv run python scripts/gen_department_specs.py

Writes (all idempotent, safe to re-run):
  specs/<service>.yaml                      one spec per department that has none yet (S03 format)
  specs/registry/routes.yaml                L1..L4 route chain per department (all 49)
  database/migrations/004_all_department_offices.sql   DEMO district + ward offices per department (ON CONFLICT DO NOTHING)
  docs/DEPARTMENT_ROUTES.md                 human-readable table of the same routes
and prints the `live_specs` block to paste into specs/registry/departments.yaml (the script also updates it in place).

EVERYTHING here is DEMO data in the same sense as database/seed.sql: department names are real government departments, the issue lists and
officer ladders are standard administrative practice (docs/specs/S09-jurisdiction.md), NOT read from any government list, and the office rows are
constructed for the demo. Confirm each ladder with a district CM Helpline branch before real use. No officer names, no contacts.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPECS = ROOT / "specs"

# (hi, en) pairs written as "hi|en"; issues as "value|hi|en".
# id: (service, offices.department, label_hi, label_en, [recognise], [issues], extra_field or None, short, l1_office, district_office, chain L1..L4)
D: dict[str, dict] = {
    "school_education": {
        "dept": "School Education Department", "hi": "स्कूल शिक्षा / मध्याह्न भोजन", "en": "School education and mid-day meal", "short": "EDU",
        "rec": ["मिड डे मील नहीं मिल रहा / mid day meal nahi mil raha / PM POSHAN", "स्कूल में शिक्षक नहीं आते / teacher absent / मास्टर साहब मारसाब नहीं आते", "स्कूल की इमारत, शौचालय, किताबें, छात्रवृत्ति / school building, toilet, books, scholarship", "school ki problem"],
        "issues": ["midday_meal|मध्याह्न भोजन नहीं मिल रहा / खराब है|Mid-day meal not served or poor quality", "teacher_absent|शिक्षक अनुपस्थित / कमी|Teacher absent or shortage", "infrastructure|स्कूल भवन, शौचालय, पानी की समस्या|School building, toilet or water problem", "books_scholarship|किताबें / छात्रवृत्ति / साइकिल नहीं मिली|Books, scholarship or cycle not received", "other|स्कूल की अन्य समस्या|Other school issue"],
        "extra": ("school_name", "स्कूल का नाम", "Name of the school"),
        "l1": "Block Education Officer Office", "dist": "District Education Officer Office",
        "chain": ["Headmaster and Cluster Academic Coordinator", "Block Education Officer", "District Education Officer / District Project Coordinator (Mid-Day Meal)", "Collector"]},
    "sc_welfare": {
        "dept": "Scheduled Caste Welfare Department", "hi": "अनुसूचित जाति कल्याण", "en": "Scheduled Caste welfare", "short": "SCW",
        "rec": ["अनुसूचित जाति की छात्रवृत्ति / SC scholarship", "छात्रावास की समस्या / hostel", "जाति प्रमाण पत्र / caste certificate SC", "SC welfare scheme ka paisa nahi mila"],
        "issues": ["scholarship|छात्रवृत्ति नहीं मिली|Scholarship not received", "hostel|छात्रावास की समस्या|Hostel problem", "scheme_benefit|योजना का लाभ नहीं मिला|Scheme benefit not received", "atrocity_relief|अत्याचार राहत राशि|Atrocity relief amount", "other|अन्य समस्या|Other issue"],
        "extra": None, "l1": "Assistant Commissioner Tribal and SC Welfare Office", "dist": "District SC Welfare Officer Office",
        "chain": ["Hostel Superintendent / Block Coordinator", "Assistant Commissioner (SC Welfare)", "District Welfare Officer / Deputy Director", "Collector"]},
    "anand": {
        "dept": "Anand Department", "hi": "आनंद विभाग", "en": "Happiness (Anand) department", "short": "ANAND",
        "rec": ["आनंद उत्सव / आनंद केंद्र / anand kendra", "happiness department", "आनंद विभाग की शिकायत"],
        "issues": ["anand_centre|आनंद केंद्र की समस्या|Anand centre problem", "programme|कार्यक्रम / प्रशिक्षण|Programme or training", "volunteer|स्वयंसेवक की समस्या|Volunteer issue", "other|अन्य|Other"],
        "extra": None, "l1": "Anand Sansthan Block Coordinator", "dist": "District Anand Coordinator Office",
        "chain": ["Block Coordinator", "District Coordinator", "Collector", "Anand Sansthan Bhopal"]},
    "ayush": {
        "dept": "AYUSH Department", "hi": "आयुष विभाग", "en": "AYUSH (Ayurveda, Unani, Homoeopathy)", "short": "AYUSH",
        "rec": ["आयुर्वेदिक अस्पताल / ayurvedic dispensary", "होम्योपैथी दवा नहीं मिल रही / homeopathy", "आयुष डॉक्टर नहीं हैं"],
        "issues": ["dispensary|औषधालय बंद / डॉक्टर अनुपस्थित|Dispensary closed or doctor absent", "medicine|दवा उपलब्ध नहीं|Medicine not available", "registration|आयुष पंजीयन / लाइसेंस|AYUSH registration or licence", "other|अन्य|Other"],
        "extra": ("institution_name", "औषधालय / अस्पताल का नाम", "Name of the dispensary or hospital"),
        "l1": "AYUSH Dispensary Medical Officer", "dist": "District AYUSH Officer Office",
        "chain": ["Dispensary Medical Officer", "District AYUSH Officer", "Joint Director AYUSH (division)", "Director AYUSH"]},
    "higher_education": {
        "dept": "Higher Education Department", "hi": "उच्च शिक्षा", "en": "Higher education, colleges, universities", "short": "HEDU",
        "rec": ["कॉलेज की समस्या / college problem", "विश्वविद्यालय परिणाम / university result", "प्रोफेसर नहीं आते / college admission scholarship"],
        "issues": ["admission|प्रवेश की समस्या|Admission problem", "result_exam|परीक्षा / रिजल्ट की समस्या|Exam or result problem", "scholarship|छात्रवृत्ति / फीस|Scholarship or fee", "college_facility|कॉलेज में सुविधा नहीं|Facilities in the college", "other|अन्य|Other"],
        "extra": ("institution_name", "कॉलेज / विश्वविद्यालय का नाम", "Name of the college or university"),
        "l1": "College Principal Office", "dist": "District Higher Education Officer Office",
        "chain": ["Principal", "Regional Additional Director (division)", "Commissioner Higher Education", "Principal Secretary"]},
    "horticulture_food_processing": {
        "dept": "Horticulture and Food Processing Department", "hi": "उद्यानिकी एवं खाद्य प्रसंस्करण", "en": "Horticulture and food processing", "short": "HORT",
        "rec": ["उद्यानिकी योजना / horticulture scheme", "फल सब्जी की खेती अनुदान / subsidy for orchard", "पॉलीहाउस ड्रिप सिंचाई अनुदान / drip subsidy"],
        "issues": ["subsidy|अनुदान नहीं मिला|Subsidy not received", "plants_seeds|पौधे / बीज की समस्या|Plants or seeds problem", "scheme_application|योजना का आवेदन अटका|Scheme application stuck", "other|अन्य|Other"],
        "extra": None, "l1": "Senior Horticulture Development Officer Office", "dist": "Deputy Director Horticulture Office",
        "chain": ["Rural Horticulture Extension Officer", "Senior Horticulture Development Officer (block)", "Deputy Director Horticulture (district)", "Director Horticulture"]},
    "industry_investment": {
        "dept": "Industrial Policy and Investment Department", "hi": "उद्योग एवं निवेश", "en": "Industry and investment", "short": "IND",
        "rec": ["उद्योग लगाने की अनुमति / industry permission", "निवेश सब्सिडी / investment subsidy", "औद्योगिक क्षेत्र में प्लॉट / industrial plot allotment"],
        "issues": ["permission|अनुमति / एनओसी अटकी|Permission or NOC stuck", "subsidy|सब्सिडी / प्रोत्साहन नहीं मिला|Subsidy or incentive not received", "plot|औद्योगिक भूखंड की समस्या|Industrial plot problem", "other|अन्य|Other"],
        "extra": None, "l1": "District Trade and Industry Centre", "dist": "General Manager District Trade and Industry Centre Office",
        "chain": ["Industrial Extension Officer", "General Manager, District Trade and Industry Centre", "Regional MPIDC / Commissioner Industries", "Principal Secretary"]},
    "agriculture": {
        "dept": "Farmer Welfare and Agriculture Department", "hi": "किसान कल्याण एवं कृषि", "en": "Farmer welfare and agriculture", "short": "AGRI",
        "rec": ["खाद बीज नहीं मिल रहा / fertiliser seed shortage", "फसल बीमा / किसान सम्मान निधि / crop insurance PM Kisan", "फसल खराब मुआवजा / crop damage compensation", "किसान की शिकायत"],
        "issues": ["fertiliser_seed|खाद / बीज नहीं मिल रहा या महंगा|Fertiliser or seed not available or overpriced", "crop_insurance|फसल बीमा / नुकसान का मुआवजा|Crop insurance or damage compensation", "kisan_samman|किसान सम्मान निधि का पैसा नहीं आया|PM Kisan payment not received", "subsidy|कृषि अनुदान / कृषि यंत्र|Agriculture subsidy or equipment", "other|अन्य|Other"],
        "extra": None, "l1": "Rural Agriculture Extension Officer / Sub-Divisional Agriculture Office", "dist": "Deputy Director Agriculture Office",
        "chain": ["Rural Agriculture Extension Officer (RAEO)", "Sub-Divisional Agriculture Officer", "Deputy Director Agriculture", "Collector / Director Agriculture"]},
    "mineral": {
        "dept": "Mineral Resources Department", "hi": "खनिज साधन", "en": "Mineral resources and mining", "short": "MIN",
        "rec": ["अवैध खनन / illegal mining", "रेत माफिया / रेत की चोरी / sand mining", "खदान से धूल या ब्लास्टिंग / quarry blasting", "ट्रैक्टर से अवैध रेत / illegal sand transport"],
        "issues": ["illegal_mining|अवैध खनन / रेत उत्खनन|Illegal mining or sand extraction", "transport|खनिज का अवैध परिवहन|Illegal mineral transport", "quarry_nuisance|खदान से नुकसान / ब्लास्टिंग|Quarry damage or blasting", "other|अन्य|Other"],
        "extra": None, "l1": "Mining Inspector Office", "dist": "District Mining Officer Office",
        "chain": ["Mining Inspector", "Mining Officer (district)", "Collector (Mining Committee)", "Director Geology and Mining"]},
    "food_civil_supplies": {
        "dept": "Food Civil Supplies Department", "hi": "खाद्य एवं नागरिक आपूर्ति (राशन)", "en": "Food and civil supplies (ration)", "short": "FCS",
        "rec": ["राशन नहीं मिल रहा / ration nahi mil raha", "राशन कार्ड नहीं बना / ration card", "राशन दुकान वाला मना करता है / fair price shop", "तौल में कम अनाज देता है"],
        "issues": ["ration_denied|राशन नहीं दिया जा रहा|Ration not given", "ration_card|राशन कार्ड नहीं बना / गलत है|Ration card not made or wrong", "short_weight|कम तौल / ज्यादा दाम|Short weight or overcharging", "shop_closed|राशन दुकान बंद या अनियमित|Fair price shop closed or irregular", "other|अन्य|Other"],
        "extra": None, "l1": "Supply Inspector / Fair Price Shop Inspector Office", "dist": "District Supply Officer Office",
        "chain": ["Supply Inspector", "Food Officer (block / tehsil)", "District Supply Officer", "Collector / Joint Commissioner Food"]},
    "home": {
        "dept": "Home Department (Police)", "hi": "गृह विभाग / पुलिस", "en": "Home department and police", "short": "POL",
        "rec": ["पुलिस थाने में सुनवाई नहीं / police not registering FIR", "चोरी, मारपीट, धोखाधड़ी / theft, assault, fraud", "साइबर ठगी / cyber fraud", "पुलिस की शिकायत"],
        "issues": ["fir_not_registered|एफआईआर दर्ज नहीं हो रही|FIR not registered", "crime|चोरी / मारपीट / अपराध|Theft, assault or other crime", "cyber_fraud|साइबर ठगी / ऑनलाइन धोखाधड़ी|Cyber or online fraud", "police_conduct|पुलिस का व्यवहार / रिश्वत|Police misconduct or bribe", "other|अन्य|Other"],
        "extra": None, "l1": "Police Station (Station House Officer)", "dist": "Superintendent of Police Office",
        "chain": ["Station House Officer", "SDOP (sub-division)", "Superintendent of Police", "DIG / IG (range)"]},
    "medical_education": {
        "dept": "Medical Education Department", "hi": "चिकित्सा शिक्षा", "en": "Medical education and medical colleges", "short": "MEDEDU",
        "rec": ["मेडिकल कॉलेज अस्पताल की समस्या / medical college hospital", "एमबीबीएस प्रवेश / MBBS admission", "मेडिकल कॉलेज में इलाज नहीं"],
        "issues": ["hospital_service|मेडिकल कॉलेज अस्पताल में इलाज / दवा|Treatment or medicine at medical-college hospital", "admission|प्रवेश / काउंसलिंग|Admission or counselling", "stipend_fee|स्टाइपेंड / फीस|Stipend or fees", "other|अन्य|Other"],
        "extra": ("institution_name", "मेडिकल कॉलेज / अस्पताल का नाम", "Name of the medical college or hospital"),
        "l1": "Medical College Hospital Superintendent Office", "dist": "Dean Medical College Office",
        "chain": ["Hospital Superintendent", "Dean, Medical College", "Directorate of Medical Education", "Principal Secretary"]},
    "tribal_affairs": {
        "dept": "Tribal Affairs Department", "hi": "जनजातीय कार्य", "en": "Tribal affairs", "short": "TRIBAL",
        "rec": ["आदिवासी छात्रावास / tribal hostel", "आदिवासी छात्रवृत्ति / tribal scholarship", "आश्रम शाला की समस्या / ashram school", "वन अधिकार पट्टा / forest rights patta"],
        "issues": ["scholarship|छात्रवृत्ति नहीं मिली|Scholarship not received", "hostel_ashram|छात्रावास / आश्रम शाला की समस्या|Hostel or ashram school problem", "forest_rights|वन अधिकार पट्टा|Forest rights patta", "scheme_benefit|योजना का लाभ नहीं मिला|Scheme benefit not received", "other|अन्य|Other"],
        "extra": None, "l1": "Assistant Commissioner Tribal Welfare Office", "dist": "District Tribal Welfare Officer Office",
        "chain": ["Hostel / Ashram Superintendent", "Assistant Commissioner Tribal Affairs", "Deputy Commissioner Tribal Affairs (district)", "Collector"]},
    "public_relations": {
        "dept": "Public Relations Department", "hi": "जनसम्पर्क", "en": "Public relations", "short": "PR",
        "rec": ["अधिमान्यता / पत्रकार की समस्या / journalist accreditation", "सरकारी विज्ञापन / government advertisement", "जनसम्पर्क विभाग की शिकायत"],
        "issues": ["accreditation|पत्रकार अधिमान्यता|Journalist accreditation", "advertisement|विज्ञापन भुगतान / सूची|Advertisement payment or empanelment", "other|अन्य|Other"],
        "extra": None, "l1": "District Public Relations Officer Office", "dist": "District Public Relations Officer Office",
        "chain": ["District Public Relations Officer", "Joint Director (division)", "Commissioner Public Relations", "Principal Secretary"]},
    "jail": {
        "dept": "Jail Department", "hi": "जेल विभाग", "en": "Jail and prisons", "short": "JAIL",
        "rec": ["जेल में कैदी से मुलाकात / prison visit", "जेल में दुर्व्यवहार / jail mistreatment", "कैदी की पैरोल / parole"],
        "issues": ["visit_interview|मुलाकात की अनुमति|Permission to meet a prisoner", "mistreatment|कैदी के साथ दुर्व्यवहार / सुविधा|Mistreatment or facilities for a prisoner", "parole_release|पैरोल / रिहाई की प्रक्रिया|Parole or release process", "other|अन्य|Other"],
        "extra": ("institution_name", "जेल का नाम", "Name of the jail"),
        "l1": "Jail Superintendent Office", "dist": "Jail Superintendent Office (district / central jail)",
        "chain": ["Jail Superintendent", "Deputy Inspector General Prisons (range)", "Director General Prisons", "Principal Secretary Home"]},
    "technical_education_skill_employment": {
        "dept": "Technical Education Skill and Employment Department", "hi": "तकनीकी शिक्षा, कौशल एवं रोजगार", "en": "Technical education, skill and employment", "short": "TECH",
        "rec": ["आईटीआई की समस्या / ITI problem", "रोजगार कार्यालय पंजीयन / employment exchange", "स्किल ट्रेनिंग प्रमाणपत्र / skill certificate", "पॉलिटेक्निक प्रवेश"],
        "issues": ["iti_polytechnic|आईटीआई / पॉलिटेक्निक की समस्या|ITI or polytechnic problem", "employment_registration|रोजगार पंजीयन / बेरोजगारी भत्ता|Employment registration or allowance", "skill_training|कौशल प्रशिक्षण / प्रमाणपत्र|Skill training or certificate", "other|अन्य|Other"],
        "extra": ("institution_name", "संस्था का नाम", "Name of the institution"),
        "l1": "ITI Principal Office", "dist": "District Employment Officer Office",
        "chain": ["Institution Principal / Employment Officer", "Joint Director Employment (division)", "Commissioner Skill Development", "Principal Secretary"]},
    "narmada_valley": {
        "dept": "Narmada Valley Development Department", "hi": "नर्मदा घाटी विकास", "en": "Narmada valley development (dams, canals, resettlement)", "short": "NVDA",
        "rec": ["नहर में पानी नहीं / canal water", "बांध विस्थापन पुनर्वास / dam oustees resettlement", "सिंचाई परियोजना / irrigation project"],
        "issues": ["canal_water|नहर का पानी नहीं आ रहा|Canal water not reaching", "resettlement|विस्थापन / पुनर्वास मुआवजा|Resettlement or compensation", "project|परियोजना की समस्या|Project problem", "other|अन्य|Other"],
        "extra": None, "l1": "Sub-Engineer Narmada Valley Office", "dist": "Executive Engineer Narmada Valley Office",
        "chain": ["Sub-Engineer", "Executive Engineer", "Chief Engineer", "Vice Chairman NVDA"]},
    "panchayat_rural_development": {
        "dept": "Panchayat and Rural Development Department", "hi": "पंचायत एवं ग्रामीण विकास", "en": "Panchayat and rural development", "short": "PRD",
        "rec": ["मनरेगा मजदूरी नहीं मिली / MGNREGA wages", "प्रधानमंत्री आवास / PM Awas gramin", "पंचायत सचिव / सरपंच की शिकायत / sarpanch complaint", "गाँव में काम नहीं मिला"],
        "issues": ["mgnrega|मनरेगा काम / मजदूरी नहीं मिली|MGNREGA work or wages not received", "awas|आवास योजना की किस्त / सूची|Housing scheme instalment or list", "panchayat_conduct|सरपंच / सचिव की शिकायत|Complaint about sarpanch or secretary", "village_works|गाँव का निर्माण कार्य / नाली / सड़क|Village works, drain or road", "other|अन्य|Other"],
        "extra": None, "l1": "Janpad Panchayat CEO Office (block)", "dist": "Zila Panchayat CEO Office",
        "chain": ["Panchayat Secretary / Rozgar Sahayak", "Janpad Panchayat CEO (block)", "Zila Panchayat CEO", "Collector / Commissioner Panchayat Raj"]},
    "transport": {
        "dept": "Transport Department", "hi": "परिवहन विभाग", "en": "Transport (RTO, licence, vehicles)", "short": "TRN",
        "rec": ["ड्राइविंग लाइसेंस नहीं बना / driving licence", "वाहन रजिस्ट्रेशन / RC / vehicle registration", "बस की समस्या / overloading bus fare", "आरटीओ में रिश्वत"],
        "issues": ["licence|ड्राइविंग लाइसेंस की समस्या|Driving licence problem", "vehicle_registration|वाहन पंजीयन / आरसी|Vehicle registration or RC", "bus_permit|बस / परमिट / किराया|Bus, permit or fare", "rto_conduct|आरटीओ कार्यालय की शिकायत|RTO office conduct", "other|अन्य|Other"],
        "extra": None, "l1": "RTO Inspector Office", "dist": "Regional Transport Officer Office",
        "chain": ["RTO Clerk / Inspector", "Regional Transport Officer", "Deputy Transport Commissioner", "Transport Commissioner (Gwalior)"]},
    "tourism": {
        "dept": "Tourism Department", "hi": "पर्यटन विभाग", "en": "Tourism", "short": "TOUR",
        "rec": ["पर्यटन स्थल की समस्या / tourist place", "एमपी टूरिज्म होटल बुकिंग / MP Tourism hotel booking", "गाइड / टूरिस्ट के साथ धोखा"],
        "issues": ["tourist_site|पर्यटन स्थल पर सुविधा / सफाई|Facilities or cleanliness at tourist site", "booking_refund|बुकिंग / रिफंड|Booking or refund", "tourist_fraud|पर्यटक के साथ धोखा|Fraud against tourists", "other|अन्य|Other"],
        "extra": None, "l1": "District Tourism Officer Office", "dist": "District Tourism Officer Office",
        "chain": ["Tourist Facilitation Officer", "Regional Manager MPSTDC", "Director Tourism", "Principal Secretary"]},
    "animal_husbandry": {
        "dept": "Animal Husbandry Department", "hi": "पशुपालन", "en": "Animal husbandry and veterinary", "short": "AH",
        "rec": ["पशु बीमार है डॉक्टर नहीं आया / veterinary doctor", "पशु टीकाकरण / vaccination of cattle", "गौशाला की समस्या / gaushala", "पशु चिकित्सालय बंद"],
        "issues": ["vet_service|पशु चिकित्सक / दवा उपलब्ध नहीं|Veterinary doctor or medicine not available", "vaccination|टीकाकरण नहीं हुआ|Vaccination not done", "gaushala|गौशाला की समस्या / अनुदान|Gaushala problem or grant", "scheme|पशुपालन योजना का लाभ|Livestock scheme benefit", "other|अन्य|Other"],
        "extra": ("institution_name", "पशु चिकित्सालय का नाम", "Name of the veterinary hospital"),
        "l1": "Veterinary Hospital / Veterinary Officer Office", "dist": "Deputy Director Animal Husbandry Office",
        "chain": ["Veterinary Field Officer", "Veterinary Officer / Assistant Director (block)", "Deputy Director Animal Husbandry (district)", "Director Animal Husbandry"]},
    "obc_minority": {
        "dept": "Backward Classes and Minority Welfare Department", "hi": "पिछड़ा वर्ग एवं अल्पसंख्यक कल्याण", "en": "Backward classes and minority welfare", "short": "OBC",
        "rec": ["ओबीसी छात्रवृत्ति / OBC scholarship", "अल्पसंख्यक योजना / minority scheme", "पिछड़ा वर्ग छात्रावास"],
        "issues": ["scholarship|छात्रवृत्ति नहीं मिली|Scholarship not received", "hostel|छात्रावास की समस्या|Hostel problem", "scheme_benefit|योजना का लाभ नहीं मिला|Scheme benefit not received", "other|अन्य|Other"],
        "extra": None, "l1": "Assistant Commissioner Backward Classes Office", "dist": "District Backward Classes Welfare Officer Office",
        "chain": ["Hostel Superintendent", "Assistant Commissioner / Block officer", "District Welfare Officer", "Collector / Commissioner"]},
    "election_commission": {
        "dept": "State Election Commission and Electoral Roll", "hi": "निर्वाचन (मतदाता सूची, चुनाव)", "en": "Elections and electoral roll", "short": "ELEC-C",
        "rec": ["वोटर आईडी नहीं बना / voter id", "मतदाता सूची में नाम नहीं / name missing in voter list", "पंचायत चुनाव की शिकायत / panchayat election", "आचार संहिता उल्लंघन"],
        "issues": ["voter_id|वोटर आईडी / नाम जोड़ना या सुधार|Voter ID, name addition or correction", "roll_missing|मतदाता सूची में नाम गायब|Name missing from the voter list", "election_conduct|चुनाव में गड़बड़ी / आचार संहिता|Election misconduct or code violation", "other|अन्य|Other"],
        "extra": None, "l1": "Booth Level Officer / Electoral Registration Officer Office", "dist": "District Election Officer Office",
        "chain": ["Booth Level Officer (BLO)", "Electoral Registration Officer (tehsil / SDM)", "District Election Officer (Collector)", "Chief Electoral Officer"]},
    "public_service_commission": {
        "dept": "Public Service Commission", "hi": "लोक सेवा आयोग (भर्ती परीक्षा)", "en": "Public Service Commission and recruitment exams", "short": "PSC",
        "rec": ["पीएससी परीक्षा परिणाम / PSC result", "भर्ती में गड़बड़ी / recruitment irregularity", "एडमिट कार्ड नहीं मिला"],
        "issues": ["exam_result|परीक्षा / परिणाम की समस्या|Exam or result problem", "form_admit|फॉर्म / प्रवेश पत्र की समस्या|Form or admit card problem", "irregularity|भर्ती में अनियमितता|Irregularity in recruitment", "other|अन्य|Other"],
        "extra": None, "l1": "MPPSC Office Indore", "dist": "MPPSC Office Indore",
        "chain": ["Section Officer, MPPSC", "Deputy Secretary", "Secretary, MPPSC", "Chairman"]},
    "women_child": {
        "dept": "Women and Child Development Department", "hi": "महिला एवं बाल विकास", "en": "Women and child development (anganwadi, nutrition)", "short": "WCD",
        "rec": ["आंगनवाड़ी में पोषण आहार नहीं / anganwadi food", "लाडली लक्ष्मी / लाड़ली बहना का पैसा नहीं आया / ladli behna", "महिला उत्पीड़न / domestic violence", "बाल विवाह / child marriage"],
        "issues": ["anganwadi_food|आंगनवाड़ी में पोषण आहार नहीं मिल रहा|Anganwadi nutrition not given", "ladli_scheme|लाड़ली लक्ष्मी / लाड़ली बहना की राशि नहीं आई|Ladli scheme amount not received", "women_safety|महिला उत्पीड़न / घरेलू हिंसा|Harassment or domestic violence", "child_protection|बाल विवाह / बाल श्रम / बच्चे की सुरक्षा|Child marriage, child labour or protection", "other|अन्य|Other"],
        "extra": ("institution_name", "आंगनवाड़ी केंद्र का नाम", "Name of the anganwadi centre"),
        "l1": "CDPO Office (Child Development Project Officer)", "dist": "District Programme Officer Women and Child Development Office",
        "chain": ["Anganwadi Supervisor", "CDPO (project / block)", "District Programme Officer", "Collector / Commissioner WCD"]},
    "planning_statistics": {
        "dept": "Planning Economics and Statistics Department", "hi": "योजना, आर्थिक एवं सांख्यिकी", "en": "Planning, economics and statistics", "short": "PES",
        "rec": ["जनगणना / सर्वे में शामिल नहीं / census survey", "सांख्यिकी विभाग की शिकायत", "विधायक निधि / MLA fund"],
        "issues": ["survey|सर्वे / गणना में नाम नहीं|Left out of a survey or count", "mla_fund|विधायक / सांसद निधि के काम|MLA or MP fund works", "other|अन्य|Other"],
        "extra": None, "l1": "District Statistics Officer Office", "dist": "District Planning Officer Office",
        "chain": ["District Statistics Officer", "District Planning Officer", "Collector", "Director Economics and Statistics"]},
    "revenue": {
        "dept": "Revenue Department", "hi": "राजस्व विभाग", "en": "Revenue (land records, certificates, patwari)", "short": "REV",
        "rec": ["नामांतरण / बंटवारा नहीं हो रहा / mutation partition", "खसरा खतौनी में गलती / land record error", "जमीन पर कब्जा / अतिक्रमण / encroachment", "पटवारी रिश्वत मांगता है / patwari bribe", "जाति या आय प्रमाणपत्र नहीं बना / certificate"],
        "issues": ["mutation|नामांतरण / बंटवारा अटका|Mutation or partition stuck", "record_error|खसरा / खतौनी में गलती|Error in khasra or khatauni", "encroachment|कब्जा / अतिक्रमण / सीमांकन|Encroachment or demarcation", "certificate|जाति / आय / निवासी प्रमाणपत्र|Caste, income or domicile certificate", "official_conduct|पटवारी / तहसीलदार रिश्वत या देरी|Patwari or Tehsildar bribe or delay", "other|अन्य|Other"],
        "extra": None, "l1": "Tehsil Office (Tehsildar)", "dist": "Sub-Divisional Magistrate Office",
        "chain": ["Patwari / Revenue Inspector", "Tehsildar", "Sub-Divisional Magistrate (SDM)", "Collector"]},
    "public_service_management": {
        "dept": "Public Service Management Department", "hi": "लोक सेवा प्रबंधन (लोक सेवा गारंटी)", "en": "Public service management (Lok Seva Guarantee)", "short": "PSM",
        "rec": ["लोक सेवा गारंटी में समय पर काम नहीं हुआ / Lok Seva guarantee delay", "सेवा का आवेदन अटका / service application stuck", "अपील अधिकारी / first appeal"],
        "issues": ["service_delay|सेवा तय समय में नहीं मिली|Notified service not delivered in time", "appeal|अपील करनी है / अपील का निर्णय|Appeal needed or decided", "kiosk_problem|लोक सेवा केंद्र की समस्या|Lok Seva Kendra problem", "other|अन्य|Other"],
        "extra": None, "l1": "Designated Officer of the concerned service", "dist": "District Public Service Management Office (Collectorate)",
        "chain": ["Designated Officer", "First Appeal Officer", "Second Appellate Authority", "Public Service Management Department Bhopal"]},
    "public_health_family_welfare": {
        "dept": "Public Health and Family Welfare Department", "hi": "स्वास्थ्य एवं परिवार कल्याण", "en": "Public health and family welfare", "short": "HLTH",
        "rec": ["अस्पताल में डॉक्टर नहीं मिलते / doctor absent hospital", "दवा उपलब्ध नहीं / medicine not available", "एम्बुलेंस नहीं आई / ambulance 108", "आयुष्मान कार्ड / Ayushman card", "टीकाकरण / vaccination"],
        "issues": ["doctor_absent|डॉक्टर / स्टाफ अनुपस्थित|Doctor or staff absent", "medicine|दवा / जाँच उपलब्ध नहीं|Medicine or test not available", "ambulance|एम्बुलेंस नहीं आई|Ambulance did not come", "ayushman_card|आयुष्मान कार्ड / इलाज का खर्च|Ayushman card or treatment cost", "vaccination_ant|टीकाकरण / जननी सुरक्षा / ए.एन.एम.|Vaccination, maternity scheme or ANM", "other|अन्य|Other"],
        "extra": ("institution_name", "अस्पताल / स्वास्थ्य केंद्र का नाम", "Name of the hospital or health centre"),
        "l1": "Block Medical Officer Office", "dist": "Chief Medical and Health Officer Office",
        "chain": ["Medical Officer (PHC / sub-health centre)", "Block Medical Officer (BMO)", "Civil Surgeon / CMHO (district)", "Joint Director / Director Health Services"]},
    "forest": {
        "dept": "Forest Department", "hi": "वन विभाग", "en": "Forest", "short": "FOR",
        "rec": ["अवैध कटाई / tree felling / illegal wood", "जंगली जानवर से नुकसान / wild animal damage", "वन विभाग का मुआवजा / forest compensation", "वन अधिकार पट्टा"],
        "issues": ["illegal_felling|पेड़ों की अवैध कटाई / लकड़ी तस्करी|Illegal tree felling or timber smuggling", "wildlife_damage|जंगली जानवर से फसल / जान को नुकसान|Wild animal crop or life damage", "compensation|मुआवजा / राहत राशि नहीं मिली|Compensation not received", "forest_rights|वन अधिकार / वन भूमि|Forest rights or forest land", "other|अन्य|Other"],
        "extra": None, "l1": "Forest Ranger Office", "dist": "Divisional Forest Officer Office",
        "chain": ["Forest Guard / Beat Guard", "Range Officer (Ranger)", "Divisional Forest Officer (DFO)", "Conservator of Forests / Collector"]},
    "commercial_tax": {
        "dept": "Commercial Tax Department", "hi": "वाणिज्यिक कर (जीएसटी)", "en": "Commercial tax and GST", "short": "CTD",
        "rec": ["जीएसटी रिफंड / GST refund", "कर अधिकारी परेशान करता है / tax officer harassment", "व्यापारी पंजीयन / dealer registration", "प्रोफेशनल टैक्स"],
        "issues": ["gst_refund|जीएसटी रिफंड / रिटर्न|GST refund or return", "registration|पंजीयन / लाइसेंस|Registration or licence", "officer_conduct|कर अधिकारी का व्यवहार / रिश्वत|Tax officer conduct or bribe", "other|अन्य|Other"],
        "extra": None, "l1": "Commercial Tax Officer Office", "dist": "Deputy Commissioner Commercial Tax Office",
        "chain": ["Commercial Tax Officer", "Assistant Commissioner", "Deputy Commissioner", "Commissioner Commercial Tax"]},
    "science_technology": {
        "dept": "Science and Technology Department", "hi": "विज्ञान एवं प्रौद्योगिकी", "en": "Science and technology (IT services)", "short": "DST",
        "rec": ["सरकारी पोर्टल काम नहीं करता / portal not working", "ई-गवर्नेंस सेवा / e-governance", "वेबसाइट एप में समस्या"],
        "issues": ["portal_down|सरकारी पोर्टल / ऐप काम नहीं कर रहा|Government portal or app not working", "kiosk|ई-सेवा केंद्र / कियोस्क समस्या|E-service kiosk problem", "other|अन्य|Other"],
        "extra": None, "l1": "District e-Governance Society Office", "dist": "District e-Governance Society Office",
        "chain": ["District e-Governance Manager", "Collector (e-Governance Society)", "MPSeDC Bhopal", "Principal Secretary Science and Technology"]},
    "finance": {
        "dept": "Finance Department and Treasury", "hi": "वित्त विभाग / कोषालय", "en": "Finance and treasury", "short": "FIN",
        "rec": ["पेंशन नहीं मिल रही कोषालय / pension treasury", "वेतन भुगतान रुका / salary payment", "जीपीएफ / GPF payment", "बिल पास नहीं हुआ"],
        "issues": ["pension_payment|पेंशन का भुगतान रुका|Pension payment stopped", "salary_gpf|वेतन / जीपीएफ भुगतान|Salary or GPF payment", "bill_payment|बिल / ठेकेदार का भुगतान|Bill or contractor payment", "other|अन्य|Other"],
        "extra": None, "l1": "Treasury Officer Office", "dist": "District Treasury Officer Office",
        "chain": ["Treasury Officer / Sub-Treasury Officer", "District Treasury Officer", "Joint Director Treasury (division)", "Commissioner Treasuries and Accounts"]},
    "law_legislative": {
        "dept": "Law and Legislative Affairs Department", "hi": "विधि एवं विधायी कार्य", "en": "Law and legislative affairs, courts", "short": "LAW",
        "rec": ["अदालत में मुकदमा / court case", "सरकारी वकील / government advocate", "लीगल एड / legal aid"],
        "issues": ["legal_aid|मुफ्त कानूनी सहायता चाहिए|Need free legal aid", "court_service|न्यायालय की सेवा / नकल|Court service or certified copy", "govt_counsel|शासकीय अधिवक्ता की शिकायत|Complaint about government counsel", "other|अन्य|Other"],
        "extra": None, "l1": "District Legal Services Authority", "dist": "District Legal Services Authority",
        "chain": ["Legal Aid Panel Lawyer", "District Legal Services Authority Secretary", "State Legal Services Authority", "Principal Secretary Law"]},
    "civil_aviation": {
        "dept": "Civil Aviation Department", "hi": "विमानन विभाग", "en": "Civil aviation", "short": "AVI",
        "rec": ["हवाई पट्टी / airstrip", "सरकारी हेलीकॉप्टर सेवा / state air service", "उड़ान सेवा की शिकायत"],
        "issues": ["airstrip|हवाई पट्टी / एयरपोर्ट की समस्या|Airstrip or airport problem", "air_service|राज्य की हवाई सेवा|State air service", "other|अन्य|Other"],
        "extra": None, "l1": "Civil Aviation Directorate Office", "dist": "Civil Aviation Directorate Office",
        "chain": ["Aerodrome Officer", "Director Civil Aviation", "Secretary Civil Aviation", "Principal Secretary"]},
    "labour": {
        "dept": "Labour Department", "hi": "श्रम विभाग", "en": "Labour", "short": "LAB",
        "rec": ["मजदूरी नहीं मिली / wages not paid", "श्रमिक पंजीयन / labour registration", "संबल योजना / sambal", "बाल मजदूरी / child labour", "फैक्ट्री में सुरक्षा नहीं"],
        "issues": ["wages|मजदूरी / वेतन नहीं मिला|Wages not paid", "registration|श्रमिक पंजीयन / कार्ड|Labour registration or card", "welfare_scheme|श्रमिक कल्याण / संबल योजना का लाभ|Labour welfare or Sambal benefit", "child_labour|बाल मजदूरी / बंधुआ मजदूरी|Child or bonded labour", "workplace_safety|कार्यस्थल पर सुरक्षा / दुर्घटना|Workplace safety or accident", "other|अन्य|Other"],
        "extra": None, "l1": "Labour Inspector Office", "dist": "Assistant Labour Commissioner Office",
        "chain": ["Labour Inspector", "Assistant Labour Commissioner", "Deputy Labour Commissioner (division)", "Labour Commissioner"]},
    "culture": {
        "dept": "Culture Department", "hi": "संस्कृति विभाग", "en": "Culture, heritage and archives", "short": "CULT",
        "rec": ["ऐतिहासिक स्मारक की देखरेख / heritage monument", "कलाकार पेंशन / artist pension", "संग्रहालय / museum"],
        "issues": ["heritage_site|स्मारक / धरोहर की देखरेख|Heritage monument upkeep", "artist_scheme|कलाकार पेंशन / सहायता|Artist pension or aid", "other|अन्य|Other"],
        "extra": None, "l1": "District Culture Officer Office", "dist": "District Culture Officer Office",
        "chain": ["Site Custodian / Culture Officer", "Director Culture", "Commissioner Culture", "Principal Secretary"]},
    "cooperative": {
        "dept": "Cooperative Department", "hi": "सहकारिता", "en": "Cooperatives (societies, credit, fair price shops)", "short": "COOP",
        "rec": ["सोसायटी से खाद या ऋण नहीं मिल रहा / society loan fertiliser", "सहकारी बैंक में पैसा फंसा / cooperative bank", "समिति में गड़बड़ी / society irregularity"],
        "issues": ["loan_credit|सहकारी ऋण / किसान क्रेडिट कार्ड|Cooperative loan or credit", "society_irregularity|समिति में गड़बड़ी / धोखाधड़ी|Irregularity or fraud in a society", "fertiliser_ration|समिति से खाद / राशन वितरण|Fertiliser or ration distribution by society", "bank_deposit|सहकारी बैंक में जमा राशि|Deposits in a cooperative bank", "other|अन्य|Other"],
        "extra": None, "l1": "Cooperative Inspector Office", "dist": "Deputy Registrar Cooperative Societies Office",
        "chain": ["Cooperative Inspector", "Assistant Registrar", "Deputy Registrar (district)", "Joint Registrar / Registrar Cooperative Societies"]},
    "social_justice_disabled": {
        "dept": "Social Justice and Disability Welfare Department", "hi": "सामाजिक न्याय एवं निःशक्तजन कल्याण", "en": "Social justice, pensions and disability welfare", "short": "SJ",
        "rec": ["वृद्धावस्था पेंशन नहीं मिल रही / old age pension", "विधवा पेंशन / widow pension", "दिव्यांग प्रमाणपत्र / disability certificate", "दिव्यांग पेंशन उपकरण"],
        "issues": ["old_age_pension|वृद्धावस्था पेंशन नहीं मिली|Old age pension not received", "widow_pension|विधवा / परित्यक्ता पेंशन|Widow or deserted woman pension", "disability_pension|दिव्यांग पेंशन / उपकरण / प्रमाणपत्र|Disability pension, device or certificate", "kanyadan_marriage|कन्यादान / विवाह सहायता|Kanyadan or marriage assistance", "other|अन्य|Other"],
        "extra": None, "l1": "Block Social Security Officer / Gram Panchayat Office", "dist": "District Social Justice Officer Office",
        "chain": ["Gram Panchayat / Nagar Nigam pension cell", "Block / Tehsil Social Security Officer", "District Social Justice Officer", "Collector / Director Social Justice"]},
    "general_administration": {
        "dept": "General Administration Department", "hi": "सामान्य प्रशासन", "en": "General administration (collectorate, certificates)", "short": "GAD",
        "rec": ["जाति प्रमाणपत्र / caste certificate", "आय प्रमाणपत्र / income certificate", "मूल निवासी प्रमाणपत्र / domicile", "कलेक्टर कार्यालय में सुनवाई नहीं"],
        "issues": ["caste_certificate|जाति प्रमाणपत्र नहीं बना / देरी|Caste certificate not issued or delayed", "income_domicile|आय / मूल निवासी प्रमाणपत्र|Income or domicile certificate", "collectorate|कलेक्ट्रेट में सुनवाई / कार्यवाही|Hearing or action at the collectorate", "other|अन्य|Other"],
        "extra": None, "l1": "Tehsil / SDM Office (Designated Officer)", "dist": "Collectorate (District Magistrate Office)",
        "chain": ["Tehsildar (Designated Officer)", "Sub-Divisional Magistrate (First Appeal)", "Collector / Additional Collector", "Divisional Commissioner"]},
    "msme": {
        "dept": "MSME Department", "hi": "सूक्ष्म, लघु एवं मध्यम उद्यम", "en": "Micro, small and medium enterprises", "short": "MSME",
        "rec": ["उद्यम पंजीयन / udyam registration", "एमएसएमई सब्सिडी / MSME subsidy", "मुख्यमंत्री युवा उद्यमी योजना / CM yuva udyami"],
        "issues": ["registration|उद्यम पंजीयन / लाइसेंस|Enterprise registration or licence", "subsidy_loan|सब्सिडी / लोन नहीं मिला|Subsidy or loan not received", "scheme|योजना का आवेदन अटका|Scheme application stuck", "other|अन्य|Other"],
        "extra": None, "l1": "District Trade and Industry Centre", "dist": "District Trade and Industry Centre",
        "chain": ["Industrial Extension Officer", "General Manager DTIC", "Director MSME", "Principal Secretary"]},
    "cottage_village_industries": {
        "dept": "Cottage and Village Industries Department", "hi": "कुटीर एवं ग्रामोद्योग", "en": "Cottage and village industries", "short": "CVI",
        "rec": ["हथकरघा / handloom", "ग्रामोद्योग लोन / village industry loan", "कारीगर योजना / artisan scheme"],
        "issues": ["loan_subsidy|ऋण / अनुदान नहीं मिला|Loan or subsidy not received", "artisan_card|कारीगर कार्ड / पंजीयन|Artisan card or registration", "other|अन्य|Other"],
        "extra": None, "l1": "District Cottage Industries Officer Office", "dist": "District Cottage Industries Officer Office",
        "chain": ["Industrial Extension Officer", "District Officer Cottage Industries", "Joint Director (division)", "Commissioner Cottage Industries"]},
    "renewable_energy": {
        "dept": "New and Renewable Energy Department", "hi": "नवीन एवं नवकरणीय ऊर्जा", "en": "New and renewable energy (solar)", "short": "RNW",
        "rec": ["सोलर पंप अनुदान / solar pump subsidy", "रूफटॉप सोलर / rooftop solar", "सोलर स्ट्रीट लाइट खराब"],
        "issues": ["solar_pump|सोलर पंप / अनुदान|Solar pump or subsidy", "rooftop_solar|रूफटॉप सोलर / नेट मीटर|Rooftop solar or net metering", "solar_light|सोलर लाइट / प्लांट खराब|Solar light or plant not working", "other|अन्य|Other"],
        "extra": None, "l1": "District Renewable Energy Officer Office", "dist": "District Renewable Energy Officer Office",
        "chain": ["Project Officer", "District Renewable Energy Officer", "General Manager MPUVN", "Principal Secretary"]},
    "fisheries": {
        "dept": "Fisheries Department", "hi": "मत्स्य पालन / मछुआ कल्याण", "en": "Fisheries and fishermen welfare", "short": "FISH",
        "rec": ["मछुआ बीमा / fishermen insurance", "तालाब पट्टा / pond lease", "मछली पालन अनुदान / fish farming subsidy"],
        "issues": ["pond_lease|तालाब पट्टा / ठेका|Pond lease or contract", "subsidy|अनुदान / बीमा नहीं मिला|Subsidy or insurance not received", "other|अन्य|Other"],
        "extra": None, "l1": "Assistant Director Fisheries Office", "dist": "Assistant Director Fisheries Office",
        "chain": ["Fisheries Extension Officer", "Assistant Director Fisheries", "Deputy Director Fisheries (division)", "Director Fisheries"]},
    "food_drug_administration": {
        "dept": "Food and Drug Administration", "hi": "खाद्य एवं औषधि प्रशासन", "en": "Food safety and drug administration", "short": "FDA",
        "rec": ["मिलावटी खाना मिठाई / adulterated food sweets", "एक्सपायरी दवा / expired medicine", "बिना लाइसेंस दवा दुकान / medical store without licence", "दूध में मिलावट"],
        "issues": ["adulteration|खाद्य पदार्थ में मिलावट|Food adulteration", "expired_medicine|एक्सपायर / नकली दवा|Expired or fake medicine", "licence|दुकान / होटल का लाइसेंस|Shop or hotel licence", "other|अन्य|Other"],
        "extra": None, "l1": "Food Safety Officer Office", "dist": "Designated Food Safety Officer Office",
        "chain": ["Food Safety Officer / Drug Inspector", "Assistant Commissioner Food Safety (district)", "Joint Commissioner (division)", "Commissioner Food and Drug Administration"]},
}

# the four departments that already have hand-written specs and offices; they only get a route chain here
LIVE = {
    "phe": {"dept": "Jal Vibhag", "chain": ["Sub-Engineer / Handpump Mechanic (PHE) or Water Works (city)", "Sub-Divisional Officer", "Executive Engineer", "Superintending Engineer / Collector"]},
    "energy": {"dept": "Bijli Vibhag", "chain": ["Junior Engineer / Lineman (Discom)", "Assistant Engineer", "Executive Engineer", "Superintending Engineer / Consumer Grievance Redressal Forum"]},
    "public_works": {"dept": "Lok Nirman Vibhag", "chain": ["Sub-Engineer", "Sub-Divisional Officer", "Executive Engineer", "Superintending Engineer / Engineer-in-Chief"]},
    "urban_development_housing": {"dept": "Nagar Nigam Sanitation", "chain": ["Sanitary Inspector / Ward Sub-Engineer", "Zone Officer / Health Officer", "Additional Commissioner", "Municipal Commissioner"]},
}

WARDS = [("1", "महात्मा गांधी", ["Mahatma Gandhi"]), ("24", "रानी कमलापति", ["Rani Kamlapati", "Habibganj"]), ("52", "मिसरोद", ["Misrod"]),
         ("60", "गोविंदपुरा", ["Govindpura"]), ("80", "सर्वधर्म कोलार", ["Sarvadharm Kolar", "Kolar Road"])]


def spec_dict(svc: str, d: dict) -> dict:
    name = d["en"]
    issues = [dict(zip(("value", "hi", "en"), s.split("|"))) for s in d["issues"]]
    extra = []
    if d["extra"]:
        key, hi, en = d["extra"]
        extra = [{"name": key, "type": "string", "required": False, "max_length": 120, "label": {"hi": hi, "en": en}, "hint": "as the citizen said it"}]
    return {
        "spec_version": 1, "service": svc, "department": d["dept"],
        "label": {"hi": d["hi"], "en": d["en"][0].upper() + d["en"][1:]},
        "recognise": d["rec"],
        "out_of_scope": {
            "examples": ["any complaint about another department", "chit-chat", "general knowledge"],
            "reply": {
                "hi": f"माफ़ कीजिए, यह {d['hi']} से जुड़ा मामला नहीं लगता। कृपया अपनी समस्या फिर से बताइए, मैं सही विभाग तक पहुँचाने में मदद करूँगा।",
                "en": f"Sorry, this does not look like a {name} matter. Please describe your problem again and I will help route it to the right department.",
            },
        },
        "pilot": {"city": "Madhya Pradesh", "wards": 5},
        "routing": {"min_confidence": 0.7, "fallback_level": "district", "fallback_status": "needs_review", "max_match_distance_km": 5},
        "confirmation": "required",
        "fields": [
            {"name": "issue_type", "type": "enum", "required": True, "label": {"hi": "समस्या", "en": "Issue"}, "values": issues,
             # short on purpose: the reply is also read aloud, so two examples instead of the whole option list
             "question": {"hi": f"आपकी क्या समस्या है? (जैसे: {issues[0]['hi'].split('/')[0].strip()}, {issues[1]['hi'].split('/')[0].strip()})",
                          "en": f"What is the problem? (for example: {issues[0]['en']}, {issues[1]['en']})"}},
            {"name": "location", "type": "location", "required": True, "ask_for": "location", "label": {"hi": "स्थान", "en": "Location"},
             "accepts": {"gps": {"lat": [-90, 90], "lng": [-180, 180]}, "place_name": {"min_length": 2, "max_length": 100}},
             "rule": "gps or place_name is enough; the jurisdiction resolver maps it to an office (S02 offices)",
             "question": {"hi": 'आपका गाँव या वार्ड कौन सा है? नाम बताइए, या "हाँ, मैं यहीं हूँ" दबाइए।',
                          "en": 'Which village or ward are you in? Tell me the name, or tap "Yes, I am here".'}},
            {"name": "duration_days", "type": "integer", "required": False, "min": 0, "max": 365, "label": {"hi": "कितने दिनों से", "en": "Days affected"},
             "hint": "'3 दिन से' -> 3, 'कल से' -> 1, 'हफ्ते भर से' -> 7"},
            *extra,
            {"name": "address_detail", "type": "string", "required": False, "max_length": 200, "label": {"hi": "पता / लैंडमार्क", "en": "Address or landmark"},
             "hint": "house, street or landmark exactly as the citizen said it"},
        ],
    }


HEADER = """# Service spec: {svc} (generated by backend/scripts/gen_department_specs.py; format docs/specs/S03-service-spec-format.md).
# DEMO routing data: the issue list is standard practice for this department, not read from a government list. The department string below is the
# same text as offices.department in database/migrations/004_all_department_offices.sql. Edit the generator, then re-run it; or edit this file by hand.
"""


class _Dumper(yaml.SafeDumper):
    pass


def main() -> None:
    written = []
    for svc, d in D.items():
        path = SPECS / f"{svc}.yaml"
        body = yaml.dump(spec_dict(svc, d), Dumper=_Dumper, allow_unicode=True, sort_keys=False, width=140, default_flow_style=None)
        path.write_text(HEADER.format(svc=svc) + body, encoding="utf-8")
        written.append(svc)

    # route chains for all departments
    routes = {}
    for svc, d in D.items():
        routes[svc] = {"department": d["dept"], "first_office": d["l1"], "district_office": d["dist"], "chain": d["chain"]}
    for dept_id, d in LIVE.items():
        routes[dept_id] = {"department": d["dept"], "first_office": "(existing DEMO offices, database/seed.sql)", "district_office": "(existing)", "chain": d["chain"]}
    (SPECS / "registry" / "routes.yaml").write_text(
        "# L1..L4 route chain per department. DEMO / standard administrative practice, NOT read from a government list; confirm with a district CM Helpline\n"
        "# branch before real use. Designations only (no officer names, no contacts). Generated by backend/scripts/gen_department_specs.py.\n"
        "# Keys are registry department ids (specs/registry/departments.yaml). Escalation timing default: 7 days per level (sources disagree, see docs/DEPARTMENT_ROUTES.md).\n"
        + yaml.dump({"escalation_days_per_level": 7, "departments": routes}, allow_unicode=True, sort_keys=False, width=140),
        encoding="utf-8")

    # offices SQL
    sql = ["-- Migration 004: DEMO offices for every department that has a generated service spec (scripts/gen_department_specs.py).",
           "-- Same demo wards as seed.sql so a place name routes the same way in every department. DEMO data, NOT from any government list.",
           "-- Safe to run twice (ON CONFLICT DO NOTHING). Undo: DELETE FROM offices WHERE office_name LIKE '%(DEMO)' AND department IN (<these departments>);",
           ""]
    q = lambda s: "'" + s.replace("'", "''") + "'"
    ward_rows, dist_rows = [], []
    for svc, d in D.items():
        for code, name, aliases in WARDS:
            al = "ARRAY[" + ", ".join(q(a) for a in aliases) + "]"
            ward_rows.append(f"  ({q(d['dept'])}, 'ward', {q(code)}, {q(name)}, {al}, NULL, NULL, {q(d['l1'] + ' - Ward ' + name + ' (DEMO)')}, NULL, true)")
        dist_rows.append(f"  ({q(d['dept'])}, 'district', {q(d['short'] + '-HQ')}, 'Bhopal', ARRAY['Bhopal'], NULL, NULL, {q(d['dist'] + ' (DEMO)')}, NULL, true)")
    cols = "(department, level, code, name, aliases, centroid_lat, centroid_lng, office_name, officer_name, active)"
    sql += [f"INSERT INTO offices {cols} VALUES", ",\n".join(dist_rows), "ON CONFLICT (department, level, code) DO NOTHING;", "",
            f"INSERT INTO offices {cols} VALUES", ",\n".join(ward_rows), "ON CONFLICT (department, level, code) DO NOTHING;", ""]
    (ROOT / "database" / "migrations" / "004_all_department_offices.sql").write_text("\n".join(sql), encoding="utf-8")

    # registry live_specs
    reg_path = SPECS / "registry" / "departments.yaml"
    text = reg_path.read_text(encoding="utf-8")
    live = {"phe": "water_supply", "energy": "electricity", "public_works": "roads", "urban_development_housing": "sanitation", **{k: k for k in D}}
    block = "live_specs:\n" + "".join(f"  {k}: {v}\n" for k, v in live.items())
    text = re.sub(r"live_specs:\n(?:  .*\n)+", block, text, count=1)
    reg_path.write_text(text, encoding="utf-8")

    # human readable routes
    names = {x["id"]: x["name_en"] for x in yaml.safe_load(text)["departments"]}
    md = ["# Department routes (DEMO)", "", ("Generated by `backend/scripts/gen_department_specs.py`. Designations only, no officer names. Standard administrative practice, **not** read from a "
          "government list: confirm each ladder with a district CM Helpline branch before real use. Default escalation: 7 days per level (sources disagree)."), "",
          "| Department | Offices.department (DEMO) | First office (ward level) | District fallback | L1 | L2 | L3 | L4 |", "|---|---|---|---|---|---|---|---|"]
    for k, r in routes.items():
        c = r["chain"]
        md.append(f"| {names.get(k, k)} | {r['department']} | {r['first_office']} | {r['district_office']} | {c[0]} | {c[1]} | {c[2]} | {c[3]} |")
    (ROOT / "docs" / "DEPARTMENT_ROUTES.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"wrote {len(written)} specs, {len(routes)} route chains, {len(ward_rows) + len(dist_rows)} office rows")


if __name__ == "__main__":
    main()
