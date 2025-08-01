# 🎯 Matchsho

**Matchsho** is a web application designed to help university students find compatible roommates in dormitories. By collecting answers to a simple psychology-based test and personal living preferences, the system recommends the most compatible matches to enhance the shared dormitory experience and reduce potential conflicts.

---

## 🚀 Tech Stack

- **Frontend**: HTML, TailwindCSS, JavaScript  
- **Backend**: Python, FastAPI  
- **Database**: MySQL

---

## ✨ Features

- 🧠 **Smart Matchmaking** – Pairs students based on personality, lifestyle, and roommate preferences.
- 📝 **Custom Test System** – Includes a personalized questionnaire system to evaluate compatibility.
- 📊 **Clear Result Display** – Shows roommate compatibility scores and match reasoning.
- ⚙️ **Modern Tech Stack** – Built with FastAPI, vanilla JavaScript, TailwindCSS, and MySQL.
- 🌐 **Web-based UI** – Simple and responsive interface accessible from any device.
- 🔐 **Privacy Focused** – All data is stored securely and only accessible by admins.

---

## ⚙️ Installation & Running Locally

Follow these steps to run Matchsho on your local machine.

### 🔧 Prerequisites

- Python 3.10+
- MySQL Server
- Git
- Any modern browser (for frontend)

### 📥 Clone the Repository

```bash
git clone https://github.com/yourusername/matchsho.git
cd matchsho
```

### Backend Setup (FastAPI)

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure `.env` with your MySQL credentials.

4. Run the backend:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

### Frontend Setup

- The frontend is a static site built with vanilla JavaScript.
- You can open `index.html` directly in your browser or serve it locally:

```bash
cd frontend
python -m http.server 8080
```

Open your browser at `http://localhost:8080`.

---

## 🧗 Challenges Faced

During the development of Matchsho, these were some of the main challenges:

### 1. 🧠 Designing the Matching Algorithm
Creating a system that accurately matches students based on a set of subjective inputs (like cleanliness, bedtime, sociability) required trial and error. We iterated over various scoring strategies before settling on a weighted comparison model.

### 2. 🔗 Connecting Vanilla JS to an API  
Since we didn’t use a frontend framework, working with async APIs and handling loading states manually in JavaScript added extra effort and complexity.

### 3. 🧵 CORS & Backend Connectivity  
Integrating the frontend with FastAPI required proper CORS configuration and consistent API route design.


### 4. 🧪 Handling Test Results  
Displaying and interpreting the personality/compatibility test results required several design iterations to make the results understandable and meaningful for students.

### 5. 🔒 Respecting User Privacy  
Even though this is a student project, user data privacy was important. We avoided storing unnecessary raw answers and made sure data was only accessible by authorized users.


---

## 🛤️ Roadmap

Here are some planned features and improvements for future versions of Matchsho:

- [ ] Add real-time chat functionality between matched roommates.
- [ ] Develop a mobile app version for easier access.
- [ ] Improve the matching algorithm with machine learning techniques.
- [ ] Add multi-language support to cater to international students.
- [ ] Implement user authentication and profile management.
- [ ] Enable admins to manage test questions and view analytics dashboards.
- [ ] Enhance accessibility compliance and UI/UX refinements.

---

## 📞 Contact

If you have any questions, suggestions, or want to contribute, feel free to reach out:

- **Email:** ehsane8224.email@example.com  
- **LinkedIn:** [linkedin.com/in/ehsan-elyasi](https://linkedin.com/in/ehsan-elyasi)  
- **GitHub:** [github.com/Ehsan24Elyasi](https://github.com/Ehsan24Elyasi)

---

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE%20.txt) file for details.

---

## 🙏 Acknowledgments

Special thanks to all students and mentors who provided valuable feedback and support during the development of this project.  
Also, thanks to the open-source community and the creators of FastAPI, TailwindCSS, and other tools used here.

---

