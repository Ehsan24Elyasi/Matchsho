const API_BASE_URL = 'http://localhost:8000';

let currentUser = JSON.parse(localStorage.getItem('currentUser')) || null;
let currentRoommateId = null;
let currentLang = localStorage.getItem('language') || 'fa';
let isNewUser = localStorage.getItem('isNewUser') === 'true' || false; 

document.documentElement.lang = currentLang;
document.documentElement.dir = currentLang === 'fa' ? 'rtl' : 'ltr';

const translations = {
    fa: {
        welcome: 'به MatchIt خوش اومدی',
        welcome_subtitle: 'هم‌اتاقی رویاهاتو با چند کلیک پیدا کن',
        login_title: 'ورود',
        signup_title: 'ثبت‌نام',
        email: 'ایمیل',
        password: 'رمز عبور',
        confirm_password: 'تأیید رمز عبور',
        login_btn: 'ورود',
        signup_btn: 'ادامه',
        required: '*فیلدهای اجباری',
        quiz_title: 'هم‌اتاقی ایده‌آلت رو پیدا کن',
        quiz_subtitle: 'جواب دادن به این سوالات به ما کمک می‌کنه تا هم‌اتاقی مناسب رو برات پیدا کنیم.',
        hygiene: 'بهداشت هم‌اتاقی برای شما چقدر اهمیت دارد؟',
        socializing: 'نسبت به رفیق بازی (آوردن دوستان به اتاق و ...) هم‌اتاقی چقدر حساسیت دارید؟',
        smoking: 'نسبت به مصرف دخانیات توسط هم‌اتاقی چقدر حساسیت دارید؟',
        noise: 'سر و صدای هم‌اتاقی برای شما چقدر اهمیت دارد؟',
        beliefs: 'اعتقادات هم‌اتاقی برای شما چقدر اهمیت دارد؟',
        sleep: 'ساعت خواب هم‌اتاقی برای شما چقدر اهمیت دارد؟',
        room_size: 'اتاق چند نفره ترجیح می‌دی؟',
        submit: 'پیدا کن!',
        results_title: 'هم‌اتاقی‌های پیشنهادی',
        results_subtitle: 'فیلترها رو تنظیم کن تا بهترین هم‌اتاقی رو پیدا کنی',
        profile_title: 'پروفایل',
        edit_test: 'ویرایش تست هم‌اتاقی',
        logout: 'خروج از حساب کاربری',
        logged_out: 'با موفقیت از حساب کاربری خارج شدید',
        room_capacity: 'ظرفیت اتاق',
        no_matches: 'هیچ هم‌اتاقی پیشنهادی یافت نشد',
        roommates_updated: 'لیست هم‌اتاقی‌های پیشنهادی به‌روزرسانی شد',
        roommate_added: 'هم‌اتاقی اضافه شد',
        roommate_rejected: 'هم‌اتاقی رد شد',
        roommate_removed: 'هم‌اتاقی حذف شد',
        profile_updated: 'پروفایل به‌روزرسانی شد',
        accept: 'پذیرش',
        reject: 'رد کردن',
        errors: {
            missing_fields: 'لطفاً تمام فیلدها را پر کنید!',
            password_mismatch: 'رمزهای عبور مطابقت ندارند!',
            email_exists: 'این ایمیل قبلاً ثبت شده است!',
            invalid_login: 'ایمیل یا رمز عبور اشتباه است!',
            user_not_found: 'کاربر یافت نشد!',
            room_full: 'اتاق پر است!',
            user_in_room: 'کاربر مورد نظر در یک اتاق قرار دارد و تمایلی به اضافه شدن به اتاق جدید ندارد',
            quiz_incomplete: 'لطفاً به تمام سوالات پاسخ دهید!',
            server_error: 'خطای سرور رخ داد، لطفاً دوباره تلاش کنید!',
            no_matches: 'هیچ هم‌اتاقی پیشنهادی یافت نشد یا خطای سرور رخ داد!'
        }
    },
    en: {
        welcome: 'Welcome to MatchIt',
        welcome_subtitle: 'Find your dream roommate with a few clicks',
        login_title: 'Login',
        signup_title: 'Sign Up',
        email: 'Email',
        password: 'Password',
        confirm_password: 'Confirm Password',
        login_btn: 'Login',
        signup_btn: 'Continue',
        required: '*Required fields',
        quiz_title: 'Find Your Ideal Roommate',
        quiz_subtitle: 'Answering these questions will help us find the perfect roommate for you.',
        hygiene: 'How important is your roommate’s hygiene to you?',
        socializing: 'How sensitive are you to your roommate’s socializing (bringing friends over, etc.)?',
        smoking: 'How sensitive are you to your roommate’s smoking habits?',
        noise: 'How important is your roommate’s noise level to you?',
        beliefs: 'How important are your roommate’s beliefs to you?',
        sleep: 'How important is your roommate’s sleep schedule to you?',
        room_size: 'What size room do you prefer?',
        submit: 'Find!',
        results_title: 'Suggested Roommates',
        results_subtitle: 'Adjust filters to find the best roommate',
        profile_title: 'Profile',
        edit_test: 'Edit Roommate Test',
        logout: 'Logout',
        logged_out: 'Logged out successfully',
        room_capacity: 'Room Capacity',
        no_matches: 'No suggested roommates found',
        roommates_updated: 'Suggested roommates updated',
        roommate_added: 'Roommate added',
        roommate_rejected: 'Roommate rejected',
        roommate_removed: 'Roommate removed',
        profile_updated: 'Profile updated',
        accept: 'Accept',
        reject: 'Reject',
        errors: {
            missing_fields: 'Please fill in all fields!',
            password_mismatch: 'Passwords do not match!',
            email_exists: 'This email is already registered!',
            invalid_login: 'Incorrect email or password!',
            user_not_found: 'User not found!',
            room_full: 'Room is full!',
            user_in_room: 'The selected user is already in a room and is not available to join a new one',
            quiz_incomplete: 'Please answer all questions!',
            server_error: 'Server error occurred, please try again!',
            no_matches: 'No suggested roommates found or server error occurred!'
        }
    }
};

const sanitizeInput = (input) => {
    const div = document.createElement('div');
    div.textContent = input;
    return div.innerHTML;
};

const debounce = (func, wait) => {
    let timeout;
    return (...args) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
};

const showError = (errorKey, sectionId = 'signup') => {
    const errorDiv = document.getElementById(sectionId + '-error');
    if (errorDiv) {
        errorDiv.textContent = translations[currentLang].errors[errorKey] || translations[currentLang].errors.server_error;
        errorDiv.classList.remove('hidden');
        setTimeout(() => errorDiv.classList.add('hidden'), 3000);
        announceChange(errorDiv.textContent);
    }
};

const announceChange = (message) => {
    const liveRegion = document.createElement('div');
    liveRegion.setAttribute('aria-live', 'polite');
    liveRegion.setAttribute('class', 'sr-only');
    liveRegion.textContent = message;
    document.body.appendChild(liveRegion);
    setTimeout(() => liveRegion.remove(), 1000);
};

const showLoading = () => {
    const loadingDiv = document.createElement('div');
    loadingDiv.id = 'loading';
    loadingDiv.innerHTML = '<p class="text-center font-fa">در حال بارگذاری...</p>';
    document.body.appendChild(loadingDiv);
};

const hideLoading = () => {
    const loadingDiv = document.getElementById('loading');
    if (loadingDiv) loadingDiv.remove();
};

const updateLanguage = () => {
    document.querySelectorAll('[data-lang]').forEach(element => {
        const key = element.getAttribute('data-lang');
        element.textContent = translations[currentLang][key] || element.textContent;
    });
    document.querySelectorAll('button[aria-label], input[aria-label]').forEach(element => {
        const label = element.getAttribute('aria-label');
        element.setAttribute('aria-label', translations[currentLang][label] || label);
    });
};

const navigateTo = (sectionId) => {
    console.log(`Navigating to ${sectionId}, currentUser:`, currentUser, `isNewUser: ${isNewUser}`);
    document.querySelectorAll('section').forEach(section => section.classList.add('hidden'));
    const targetSection = document.getElementById(sectionId);
    if (targetSection) {
        targetSection.classList.remove('hidden');
        window.scrollTo({ top: 0, behavior: 'smooth' });
        updateNavigation(sectionId);
        renderNavigation();
        if (sectionId === 'quiz') {
            loadQuizQuestions();
        } else if (sectionId === 'roommates' && currentUser && !isNewUser) {
            displaySuggestedRoommates();
        } else if (sectionId === 'home' && currentUser && !isNewUser) {
            updateRoomCapacity();
        } else if (sectionId === 'profile' && currentUser) {
            updateProfilePage();
        }
    } else {
        console.error(`Section ${sectionId} not found`);
        showError('user_not_found');
    }
};

const updateNavigation = (sectionId) => {
    const sectionsWithNav = ['home', 'roommates', 'profile', 'quiz', 'roommate-profile'];
    if (sectionsWithNav.includes(sectionId)) {
        document.querySelectorAll('.bottom-nav button').forEach(button => {
            button.classList.remove('active', 'text-blue-500');
            button.classList.add('text-gray-500');
            button.querySelector('svg').setAttribute('stroke-width', '2');
        });

        const activeButtonMap = {
            'home': 'home',
            'quiz': 'home',
            'roommate-profile': 'home',
            'roommates': 'roommates',
            'profile': 'profile'
        };

        const activeButton = document.querySelector(`.bottom-nav button[onclick="navigateTo('${activeButtonMap[sectionId]}')"]`);
        if (activeButton) {
            activeButton.classList.add('active', 'text-blue-500');
            activeButton.classList.remove('text-gray-500');
            activeButton.querySelector('svg').setAttribute('stroke-width', '3');
        }
    }
};

const renderNavigation = () => {
    const navSections = ['home', 'roommates', 'profile', 'quiz', 'roommate-profile'];
    navSections.forEach(sectionId => {
        const section = document.getElementById(sectionId);
        if (section && !section.querySelector('.bottom-nav')) {
            const nav = document.createElement('nav');
            nav.className = 'fixed bottom-nav bg-white shadow flex justify-around';
            nav.innerHTML = `
                <button onclick="navigateTo('home')" class="text-gray-500 flex flex-col items-center ${sectionId === 'home' || sectionId === 'quiz' || sectionId === 'roommate-profile' ? 'active text-blue-500' : ''}">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-label="خانه">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="${sectionId === 'home' || sectionId === 'quiz' || sectionId === 'roommate-profile' ? '3' : '2'}" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
                    </svg>
                    <span class="text-xs mt-1 font-fa" data-lang="home">خانه</span>
                </button>
                <button onclick="navigateTo('roommates')" class="text-gray-500 flex flex-col items-center ${sectionId === 'roommates' ? 'active text-blue-500' : ''}">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-label="هم‌اتاقی">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="${sectionId === 'roommates' ? '3' : '2'}" d="M17 8h2a2 2 0 012 2v6a2 2 0 01-2 2h-2m-4 0H7a2 2 0 01-2-2v-6a2 2 0 012-2h2m4 0V6a2 2 0 00-2-2H7a2 2 0 00-2 2v2m12-2V6a2 2 0 00-2-2h-2" />
                    </svg>
                    <span class="text-xs mt-1 font-fa" data-lang="roommates">هم‌اتاقی</span>
                </button>
                <button onclick="navigateTo('profile')" class="text-gray-500 flex flex-col items-center ${sectionId === 'profile' ? 'active text-blue-500' : ''}">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-label="پروفایل">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="${sectionId === 'profile' ? '3' : '2'}" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                    </svg>
                    <span class="text-xs mt-1 font-fa" data-lang="profile">پروفایل</span>
                </button>
            `;
            section.appendChild(nav);
        }
    });
};

const handleThemeToggle = debounce(() => {
    document.body.classList.toggle('dark-mode');
    localStorage.setItem('theme', document.body.classList.contains('dark-mode') ? 'dark' : 'light');
    announceChange(translations[currentLang].theme_changed || 'Theme changed');
}, 200);

const handleLanguageToggle = debounce(() => {
    currentLang = currentLang === 'fa' ? 'en' : 'fa';
    localStorage.setItem('language', currentLang);
    document.documentElement.lang = currentLang;
    document.documentElement.dir = currentLang === 'fa' ? 'rtl' : 'ltr';
    updateLanguage();
    announceChange(translations[currentLang].language_changed || 'Language changed');
}, 200);

const handleLogout = () => {
    localStorage.removeItem('currentUser');
    localStorage.removeItem('isNewUser');
    currentUser = null;
    isNewUser = false;
    navigateTo('login');
    announceChange(translations[currentLang].logged_out);
};

const handleLogin = async () => {
    const email = sanitizeInput(document.getElementById('login-email').value.trim());
    const password = sanitizeInput(document.getElementById('login-password').value.trim());

    try {
        showLoading();
        console.log('Attempting login with:', { email });
        const response = await fetch(`${API_BASE_URL}/login/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Login failed');
        }
        currentUser = await response.json();
        console.log('Login successful:', currentUser);
        localStorage.setItem('currentUser', JSON.stringify(currentUser));
        localStorage.setItem('isNewUser', 'false');
        isNewUser = false;
        navigateTo('home');
        updateProfilePage();
        updateRoomCapacity();
        displaySuggestedRoommates();
    } catch (error) {
        console.error('Login error:', error.message);
        showError('invalid_login', 'login');
    } finally {
        hideLoading();
    }
};

const saveUserInfo = async () => {
    const email = sanitizeInput(document.getElementById('signup-email').value.trim());
    const password = sanitizeInput(document.getElementById('signup-password').value.trim());
    const confirmPassword = sanitizeInput(document.getElementById('signup-confirm-password').value.trim());
    const name = sanitizeInput(document.getElementById('register-name').value.trim());
    const className = sanitizeInput(document.getElementById('register-class').value.trim());
    const studentId = sanitizeInput(document.getElementById('register-student-id').value.trim());
    const genderMap = { 'مرد': 'male', 'زن': 'female' };
    const gender = genderMap[document.getElementById('register-gender').value] || document.getElementById('register-gender').value;

    if (!email || !password || !confirmPassword || !name || !className || !studentId || !gender) {
        showError('missing_fields', 'signup');
        return;
    }

    if (password !== confirmPassword) {
        showError('password_mismatch', 'signup');
        return;
    }

    try {
        showLoading();
        console.log('Attempting to register user:', { email, name, className, studentId, gender });
        const response = await fetch(`${API_BASE_URL}/users/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                email,
                password,
                name,
                class_name: className,
                student_id: studentId,
                gender
            })
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Signup failed');
        }
        currentUser = await response.json();
        console.log('User registered successfully:', currentUser);
        localStorage.setItem('currentUser', JSON.stringify(currentUser));
        localStorage.setItem('isNewUser', 'true');
        isNewUser = true;
        navigateTo('quiz');
    } catch (error) {
        console.error('Signup error:', error.message);
        showError(error.message.includes('ایمیل') ? 'email_exists' : 'missing_fields', 'signup');
    } finally {
        hideLoading();
    }
};

const loadQuizQuestions = async () => {
    console.log('Loading quiz questions...');
    const cachedQuestions = localStorage.getItem('questions');
    if (cachedQuestions) {
        const questions = JSON.parse(cachedQuestions);
        renderQuestions(questions);
        return;
    }
    try {
        showLoading();
        const response = await fetch(`${API_BASE_URL}/questions/`);
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Failed to load questions');
        }
        const questions = await response.json();
        localStorage.setItem('questions', JSON.stringify(questions));
        renderQuestions(questions);
    } catch (error) {
        console.error('Quiz questions error:', error.message);
        showError('quiz_incomplete', 'quiz');
    } finally {
        hideLoading();
    }
};

const renderQuestions = (questions) => {
    console.log('Rendering quiz questions:', questions);
    const quizDiv = document.getElementById('quiz-questions');
    if (!quizDiv) {
        console.error('Quiz questions div not found');
        return;
    }
    quizDiv.innerHTML = '';
    questions.forEach((q, index) => {
        const questionId = q.id;
        const isRoomSize = questionId === 7;
        const options = isRoomSize ? [2, 4, 8, 12] : [1, 2, 3, 4, 5];
        const fieldName = isRoomSize ? 'room_size' : `question_${questionId}`;
        const html = `
            <div class="mb-6">
                <label class="block text-gray-700 font-fa">${sanitizeInput(q.text)}</label>
                <div class="flex space-x-2 mt-2">
                    ${options.map(value => `
                        <input type="radio" name="${fieldName}" id="${fieldName}_${value}" value="${value}" class="hidden">
                        <label for="${fieldName}_${value}" class="flex-1 p-2 border rounded-lg text-center cursor-pointer font-fa">${value}</label>
                    `).join('')}
                </div>
            </div>
        `;
        quizDiv.insertAdjacentHTML('beforeend', html);
    });
};

const saveQuizResults = async () => {
    const answers = [];
    const questionIds = [1, 2, 3, 4, 5, 6, 7];
    for (const qid of questionIds) {
        const fieldName = qid === 7 ? 'room_size' : `question_${qid}`;
        const value = document.querySelector(`input[name="${fieldName}"]:checked`)?.value;
        if (!value) {
            showError('quiz_incomplete', 'quiz');
            return;
        }
        answers.push({
            user_id: currentUser.id,
            question_id: qid,
            value: parseInt(value)
        });
    }

    try {
        showLoading();
        console.log('Saving quiz answers:', answers);
        const response = await fetch(`${API_BASE_URL}/answers/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(answers)
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Failed to save answers');
        }
        localStorage.setItem('isNewUser', 'false');
        isNewUser = false;
        navigateTo('home');
        updateProfilePage();
        updateRoomCapacity();
        displaySuggestedRoommates();
    } catch (error) {
        console.error('Save quiz error:', error.message);
        showError('quiz_incomplete', 'quiz');
    } finally {
        hideLoading();
    }
};

const updateProfilePage = async () => {
    if (!currentUser) return;
    try {
        showLoading();
        const response = await fetch(`${API_BASE_URL}/users/${currentUser.id}`);
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'User not found');
        }
        const user = await response.json();
        const answersResponse = await fetch(`${API_BASE_URL}/answers/?user_id=${currentUser.id}`);
        if (!answersResponse.ok) {
            const errorData = await answersResponse.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Answers not found');
        }
        const answers = await answersResponse.json();

        const fields = {
            'profile-name': user.name || '-',
            'profile-class': user.class_name || '-',
            'profile-student-id': user.student_id || '-',
            'profile-gender': user.gender === 'male' ? 'مرد' : user.gender === 'female' ? 'زن' : '-',
            'profile-email': user.email || '-',
            'hygiene-result': answers.find(a => a.question_id === 1)?.value?.toString() || '-',
            'socializing-result': answers.find(a => a.question_id === 2)?.value?.toString() || '-',
            'smoking-result': answers.find(a => a.question_id === 3)?.value?.toString() || '-',
            'noise-result': answers.find(a => a.question_id === 4)?.value?.toString() || '-',
            'beliefs-result': answers.find(a => a.question_id === 5)?.value?.toString() || '-',
            'sleep-result': answers.find(a => a.question_id === 6)?.value?.toString() || '-'
        };

        Object.entries(fields).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) element.textContent = value;
        });

        announceChange(translations[currentLang].profile_updated);
    } catch (error) {
        console.error('Profile update error:', error.message);
        showError('user_not_found', 'profile');
    } finally {
        hideLoading();
    }
};

const updateRoomCapacity = async () => {
    if (!currentUser) {
        console.error('No currentUser found');
        return;
    }
    try {
        showLoading();
        console.log(`Fetching room data for user ${currentUser.id}`);
        const response = await fetch(`${API_BASE_URL}/rooms/${currentUser.id}`, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' }
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Room not found');
        }
        const room = await response.json();
        console.log('Room data:', room);

        const capacityBar = document.getElementById('capacity-bar');
        const capacityText = document.getElementById('capacity-text');
        const currentRoommatesDiv = document.getElementById('current-roommates');

        if (!capacityBar || !capacityText || !currentRoommatesDiv) {
            console.error('Required DOM elements not found:', {
                capacityBar: !!capacityBar,
                capacityText: !!capacityText,
                currentRoommatesDiv: !!currentRoommatesDiv
            });
            showError('server_error', 'home');
            return;
        }

        const roommates = room.roommates || [];
        console.log('Roommates:', roommates);
        const capacity = room.capacity || 1;
        const percentage = (roommates.length / capacity) * 100;

        capacityBar.style.width = `${percentage}%`;
        capacityText.textContent = `${roommates.length} از ${capacity} نفر`;

        currentRoommatesDiv.innerHTML = '';
        if (roommates.length === 0) {
            currentRoommatesDiv.innerHTML = '<p class="text-center text-gray-600 font-fa">هیچ هم‌اتاقی فعلی وجود ندارد.</p>';
            console.log('No roommates found');
        } else {
            const matchPromises = roommates.map(async (roommate) => {
                console.log('Processing roommate:', roommate);
                if (!roommate.user || !roommate.user.id) {
                    console.warn(`Roommate ${roommate.id} has invalid or missing user data:`, roommate.user);
                    return null;
                }
                let matchPercentage = null;
                try {
                    const matchResponse = await fetch(`${API_BASE_URL}/match_percentage/${currentUser.id}/${roommate.user.id}`);
                    if (matchResponse.ok) {
                        matchPercentage = await matchResponse.json();
                    } else {
                        console.warn(`Failed to fetch match percentage for user ${roommate.user.id}`);
                    }
                } catch (error) {
                    console.error(`Error fetching match percentage for roommate ${roommate.id}:`, error.message);
                }
                return {
                    user: roommate.user,
                    matchPercentage: matchPercentage || 'N/A',
                    roommateId: roommate.id
                };
            });

            const roommateData = (await Promise.all(matchPromises)).filter(data => data !== null);
            console.log('Filtered roommate data:', roommateData);

            if (roommateData.length === 0) {
                currentRoommatesDiv.innerHTML = '<p class="text-center text-gray-600 font-fa">هیچ هم‌اتاقی فعلی وجود ندارد.</p>';
                console.log('No valid roommate data after filtering');
            } else {
                roommateData.forEach(data => {
                    const card = document.createElement('div');
                    card.className = 'roommate-card';
                    card.innerHTML = `
                        <div class="profile-container">
                            ${data.matchPercentage !== 'N/A' ? `
                            <svg class="progress-circle" viewBox="0 0 100 100" aria-label="درصد تطابق">
                                <circle cx="50" cy="50" r="40" fill="none" stroke="#e5e7eb" stroke-width="10"/>
                                <circle cx="50" cy="50" r="40" fill="none" stroke="#3b82f6" stroke-width="10" stroke-dasharray="${data.matchPercentage * 2.51}, 251.2"/>
                            </svg>
                            ` : ''}
                            <svg class="profile-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-label="آیکون پروفایل">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                            </svg>
                            <span class="match-percentage">${data.matchPercentage !== 'N/A' ? data.matchPercentage + '%' : 'N/A'}</span>
                        </div>
                        <h3 class="text-sm font-semibold text-gray-800 font-fa mt-4">${sanitizeInput(data.user.name)}</h3>
                        <p class="text-xs text-gray-600 font-fa">${sanitizeInput(data.user.class_name)}</p>
                        <button onclick="removeRoommate(${data.roommateId})" class="remove-roommate-btn mt-2 font-fa">حذف</button>
                    `;
                    currentRoommatesDiv.appendChild(card);
                });
            }
        }

        announceChange(translations[currentLang].room_capacity_updated || 'Room capacity updated');
    } catch (error) {
        console.error('Room capacity error:', error.message);
        showError('user_not_found', 'home');
        const currentRoommatesDiv = document.getElementById('current-roommates');
        if (currentRoommatesDiv) {
            currentRoommatesDiv.innerHTML = '<p class="text-center text-gray-600 font-fa">خطا در بارگذاری هم‌اتاقی‌ها.</p>';
        }
    } finally {
        hideLoading();
    }
};

const displaySuggestedRoommates = async () => {
    if (!currentUser || !currentUser.id) {
        console.error('No valid currentUser found');
        showError('user_not_found', 'roommates');
        return;
    }
    showLoading();
    try {
        console.log(`Fetching matches for user ${currentUser.id}`);
        const response = await fetch(`${API_BASE_URL}/matches/${currentUser.id}`);
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Failed to fetch matches');
        }
        const matches = await response.json();
        const suggestedRoommatesDiv = document.getElementById('suggested-roommates');
        if (!suggestedRoommatesDiv) {
            console.error('Element with ID "suggested-roommates" not found');
            showError('server_error', 'roommates');
            return;
        }
        suggestedRoommatesDiv.innerHTML = '';

        if (matches.length === 0) {
            suggestedRoommatesDiv.innerHTML = `<p class="text-center text-gray-600 font-fa">${translations[currentLang].no_matches}</p>`;
            announceChange(translations[currentLang].no_matches);
            return;
        }

        matches.forEach(match => {
            const user = match.user;
            const card = document.createElement('div');
            card.className = 'roommate-card cursor-pointer';
            card.addEventListener('click', () => viewRoommateProfile(user.id));
            card.innerHTML = `
                <div class="profile-container">
                    <svg class="progress-circle" viewBox="0 0 100 100" aria-label="درصد تطابق">
                        <circle cx="50" cy="50" r="40" fill="none" stroke="#e5e7eb" stroke-width="10"/>
                        <circle cx="50" cy="50" r="40" fill="none" stroke="#3b82f6" stroke-width="10" stroke-dasharray="${match.match_percentage * 2.51}, 251.2"/>
                    </svg>
                    <svg class="profile-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-label="آیکون پروفایل">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                    </svg>
                    <span class="match-percentage">${match.match_percentage}%</span>
                </div>
                <h3 class="text-sm font-semibold text-gray-800 font-fa mt-4">${sanitizeInput(user.name)}</h3>
                <p class="text-xs text-gray-600 font-fa">${sanitizeInput(user.class_name)}</p>
            `;
            suggestedRoommatesDiv.appendChild(card);
        });

        announceChange(translations[currentLang].roommates_updated);
    } catch (error) {
        console.error('Suggested roommates error:', error.message);
        showError('no_matches', 'roommates');
    } finally {
        hideLoading();
    }
};

const viewRoommateProfile = async (roommateId) => {
    currentRoommateId = roommateId;
    try {
        showLoading();
        const response = await fetch(`${API_BASE_URL}/users/${roommateId}`);
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'User not found');
        }
        const roommate = await response.json();
        const answersResponse = await fetch(`${API_BASE_URL}/answers/?user_id=${roommateId}`);
        if (!answersResponse.ok) {
            const errorData = await answersResponse.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Answers not found');
        }
        const answers = await answersResponse.json();

        const fields = {
            'roommate-name': roommate.name || '-',
            'roommate-description': roommate.class_name || '-',
            'roommate-sleep-result': answers.find(a => a.question_id === 6)?.value?.toString() || '-',
            'roommate-cleanliness-result': answers.find(a => a.question_id === 1)?.value?.toString() || '-',
            'roommate-social-result': answers.find(a => a.question_id === 2)?.value?.toString() || '-',
            'roommate-smoking-result': answers.find(a => a.question_id === 3)?.value?.toString() || '-',
            'roommate-noise-result': answers.find(a => a.question_id === 4)?.value?.toString() || '-',
            'roommate-beliefs-result': answers.find(a => a.question_id === 5)?.value?.toString() || '-'
        };

        Object.entries(fields).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) element.textContent = value;
        });

        navigateTo('roommate-profile');
    } catch (error) {
        console.error('View roommate profile error:', error.message);
        showError('user_not_found', 'roommate-profile');
    } finally {
        hideLoading();
    }
};

const acceptRoommate = async () => {
    if (!currentUser || !currentRoommateId) {
        console.error('Missing currentUser or currentRoommateId', { currentUser, currentRoommateId });
        showError('user_not_found', 'roommate-profile');
        return;
    }
    showLoading();
    try {
        console.log(`Accepting roommate ${currentRoommateId} for user ${currentUser.id}`);
        const roomResponse = await fetch(`${API_BASE_URL}/rooms/${currentUser.id}`, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' }
        });
        if (!roomResponse.ok) {
            const errorData = await roomResponse.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Room not found');
        }
        const room = await roomResponse.json();
        console.log('Room for adding roommate:', room);
        const response = await fetch(`${API_BASE_URL}/roommates/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: currentRoommateId, room_id: room.id })
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Failed to add roommate');
        }
        const newRoommate = await response.json();
        console.log('New roommate added:', newRoommate);
        navigateTo('home');
        updateRoomCapacity();
        displaySuggestedRoommates();
        announceChange(translations[currentLang].roommate_added);
    } catch (error) {
        console.error('Accept roommate error:', error.message);
        showError(error.message.includes('ظرفیت') ? 'room_full' : error.message.includes('تمایلی') ? 'user_in_room' : 'server_error', 'roommate-profile');
    } finally {
        hideLoading();
    }
};

const rejectRoommate = async () => {
    if (!currentUser || !currentRoommateId) {
        console.error('Missing currentUser or currentRoommateId');
        showError('user_not_found', 'roommate-profile');
        return;
    }
    showLoading();
    try {
        console.log(`Rejecting roommate ${currentRoommateId} by user ${currentUser.id}`);
        const response = await fetch(`${API_BASE_URL}/reject_roommate/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: currentRoommateId, room_id: currentUser.id })
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Failed to reject roommate');
        }
        navigateTo('roommates');
        displaySuggestedRoommates();
        announceChange(translations[currentLang].roommate_rejected);
    } catch (error) {
        console.error('Reject roommate error:', error.message);
        showError('server_error', 'roommate-profile');
    } finally {
        hideLoading();
    }
};

const removeRoommate = async (roommateId) => {
    try {
        showLoading();
        console.log(`Removing roommate ${roommateId}`);
        const response = await fetch(`${API_BASE_URL}/roommates/${roommateId}`, {
            method: 'DELETE'
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Failed to remove roommate');
        }
        updateRoomCapacity();
        announceChange(translations[currentLang].roommate_removed);
    } catch (error) {
        console.error('Remove roommate error:', error.message);
        showError('user_not_found', 'home');
    } finally {
        hideLoading();
    }
};

document.addEventListener('DOMContentLoaded', () => {
    console.log('DOMContentLoaded triggered, currentUser:', currentUser, 'isNewUser:', isNewUser);
    if (localStorage.getItem('theme') === 'dark') {
        document.body.classList.add('dark-mode');
    }

    updateLanguage();

    const maleButton = document.getElementById('gender-male');
    const femaleButton = document.getElementById('gender-female');
    const genderInput = document.getElementById('register-gender');

    if (maleButton && femaleButton && genderInput) {
        maleButton.addEventListener('click', () => {
            maleButton.classList.add('active');
            femaleButton.classList.remove('active');
            genderInput.value = 'مرد';
        });

        femaleButton.addEventListener('click', () => {
            femaleButton.classList.add('active');
            maleButton.classList.remove('active');
            genderInput.value = 'زن';
        });
    }

    if (!currentUser) {
        console.log('No currentUser, navigating to splash');
        navigateTo('splash');
        setTimeout(() => navigateTo('login'), 2000);
    } else if (isNewUser) {
        console.log('New user, navigating to quiz');
        navigateTo('quiz');
    } else {
        console.log('Existing user, navigating to home');
        navigateTo('home');
    }

    renderNavigation();
});