const API_BASE_URL = 'http://localhost:8000';

let currentUser = JSON.parse(localStorage.getItem('currentUser')) || null;
let currentRoommateId = null;
let isNewUser = localStorage.getItem('isNewUser') === 'true' || false;

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

const showError = (message) => {
    let errorContainer = document.getElementById('error-container');
    if (!errorContainer) {
        errorContainer = document.createElement('div');
        errorContainer.id = 'error-container';
        errorContainer.className = 'error-message';
        document.body.prepend(errorContainer);
    }
    errorContainer.textContent = message;
    errorContainer.style.display = 'block';
    setTimeout(() => { errorContainer.style.display = 'none'; }, 3000);
};

const showLoading = () => {
    let loadingDiv = document.getElementById('loading');
    if (!loadingDiv) {
        loadingDiv = document.createElement('div');
        loadingDiv.id = 'loading';
        loadingDiv.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
        loadingDiv.innerHTML = '<p class="text-white text-xl font-fa">در حال بارگذاری...</p>';
        document.body.appendChild(loadingDiv);
    }
};

const hideLoading = () => {
    const loadingDiv = document.getElementById('loading');
    if (loadingDiv) loadingDiv.remove();
};


// --- Navigation ---

const navigateTo = (sectionId) => {
    document.querySelectorAll('section').forEach(section => section.classList.add('hidden'));
    const targetSection = document.getElementById(sectionId);
    if (targetSection) {
        targetSection.classList.remove('hidden');
        window.scrollTo({ top: 0, behavior: 'smooth' });
        window.location.hash = sectionId;

        if (!['login', 'signup', 'quiz'].includes(sectionId)) {
            updateNavigation(sectionId);
        }

        // Load section data
        if (sectionId === 'roommates' && currentUser && !isNewUser) {
            displaySuggestedRoommates();
        } else if (sectionId === 'home' && currentUser) {
            loadGroupInfo();
        } else if (sectionId === 'profile' && currentUser) {
            updateProfilePage();
        } else if (sectionId === 'requests' && currentUser) {
            loadRequests();
        } else if (sectionId === 'rooms') {
            loadRooms();
        } else if (sectionId === 'quiz') {
            loadQuizQuestions();
        }
    }
};

const updateNavigation = (sectionId) => {
    document.querySelectorAll('.bottom-nav button').forEach(button => {
        button.classList.remove('active', 'text-blue-500');
        button.classList.add('text-gray-500');
        const svg = button.querySelector('svg');
        if (svg) svg.setAttribute('stroke-width', '2');
    });

    const activeButtonMap = {
        'home': 'home',
        'roommate-profile': 'home',
        'roommates': 'roommates',
        'requests': 'requests',
        'rooms': 'rooms',
        'profile': 'profile'
    };

    const activeBtn = document.querySelector(`.bottom-nav button[data-nav="${activeButtonMap[sectionId] || sectionId}"]`);
    if (activeBtn) {
        activeBtn.classList.add('active', 'text-blue-500');
        activeBtn.classList.remove('text-gray-500');
        const svg = activeBtn.querySelector('svg');
        if (svg) svg.setAttribute('stroke-width', '3');
    }
};

const renderNavigation = () => {
    const navSections = ['home', 'roommates', 'requests', 'rooms', 'profile', 'roommate-profile'];
    navSections.forEach(sectionId => {
        const section = document.getElementById(sectionId);
        if (section && !section.querySelector('.bottom-nav')) {
            const nav = document.createElement('nav');
            nav.className = 'fixed bottom-nav bg-white shadow flex justify-around';
            nav.innerHTML = `
                <button data-nav="home" onclick="navigateTo('home')" class="text-gray-500 flex flex-col items-center">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
                    </svg>
                    <span class="text-xs mt-1 font-fa">خانه</span>
                </button>
                <button data-nav="roommates" onclick="navigateTo('roommates')" class="text-gray-500 flex flex-col items-center">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 8h2a2 2 0 012 2v6a2 2 0 01-2 2h-2m-4 0H7a2 2 0 01-2-2v-6a2 2 0 012-2h2m4 0V6a2 2 0 00-2-2H7a2 2 0 00-2 2v2m12-2V6a2 2 0 00-2-2h-2" />
                    </svg>
                    <span class="text-xs mt-1 font-fa">مچ‌ها</span>
                </button>
                <button data-nav="requests" onclick="navigateTo('requests')" class="text-gray-500 flex flex-col items-center">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                    </svg>
                    <span class="text-xs mt-1 font-fa">درخواست‌ها</span>
                </button>
                <button data-nav="rooms" onclick="navigateTo('rooms')" class="text-gray-500 flex flex-col items-center">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                    </svg>
                    <span class="text-xs mt-1 font-fa">اتاق‌ها</span>
                </button>
                <button data-nav="profile" onclick="navigateTo('profile')" class="text-gray-500 flex flex-col items-center">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                    </svg>
                    <span class="text-xs mt-1 font-fa">پروفایل</span>
                </button>
            `;
            section.appendChild(nav);
        }
    });
};


// --- Auth ---

const handleLogin = async () => {
    const email = sanitizeInput(document.getElementById('login-email').value.trim());
    const password = document.getElementById('login-password').value.trim();

    try {
        showLoading();
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
        localStorage.setItem('currentUser', JSON.stringify(currentUser));
        localStorage.setItem('isNewUser', 'false');
        isNewUser = false;
        navigateTo('home');
    } catch (error) {
        showError(error.message || 'ایمیل یا رمز عبور اشتباه است');
    } finally {
        hideLoading();
    }
};

const saveUserInfo = async () => {
    const email = sanitizeInput(document.getElementById('signup-email').value.trim());
    const password = document.getElementById('signup-password').value.trim();
    const confirmPassword = document.getElementById('signup-confirm-password').value.trim();
    const name = sanitizeInput(document.getElementById('register-name').value.trim());
    const className = sanitizeInput(document.getElementById('register-class').value.trim());
    const studentId = sanitizeInput(document.getElementById('register-student-id').value.trim());
    const genderMap = { 'مرد': 'male', 'زن': 'female' };
    const gender = genderMap[document.getElementById('register-gender').value] || document.getElementById('register-gender').value;

    if (!email || !password || !confirmPassword || !name || !className || !studentId || !gender) {
        showError('لطفاً تمام فیلدها را پر کنید');
        return;
    }
    if (password !== confirmPassword) {
        showError('رمزهای عبور مطابقت ندارند');
        return;
    }

    try {
        showLoading();
        const response = await fetch(`${API_BASE_URL}/users/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password, name, class_name: className, student_id: studentId, gender })
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Signup failed');
        }
        currentUser = await response.json();
        localStorage.setItem('currentUser', JSON.stringify(currentUser));
        localStorage.setItem('isNewUser', 'true');
        isNewUser = true;
        navigateTo('quiz');
    } catch (error) {
        showError(error.message);
    } finally {
        hideLoading();
    }
};

const handleLogout = () => {
    localStorage.removeItem('currentUser');
    localStorage.removeItem('isNewUser');
    currentUser = null;
    isNewUser = false;
    navigateTo('login');
};


// --- Quiz ---

const loadQuizQuestions = async () => {
    const cachedQuestions = localStorage.getItem('questions');
    if (cachedQuestions) {
        renderQuestions(JSON.parse(cachedQuestions));
        return;
    }
    try {
        showLoading();
        const response = await fetch(`${API_BASE_URL}/questions/`);
        if (!response.ok) throw new Error('Failed to load questions');
        const questions = await response.json();
        localStorage.setItem('questions', JSON.stringify(questions));
        renderQuestions(questions);
    } catch (error) {
        showError('خطا در بارگذاری سوالات');
    } finally {
        hideLoading();
    }
};

const renderQuestions = (questions) => {
    const quizDiv = document.getElementById('quiz-questions');
    if (!quizDiv) return;
    quizDiv.innerHTML = '';
    questions.forEach((q) => {
        const isRoomSize = q.id === 7;
        const options = isRoomSize ? [2, 4, 8, 12] : [1, 2, 3, 4, 5];
        const fieldName = isRoomSize ? 'room_size' : `question_${q.id}`;
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
            showError('لطفاً به تمام سوالات پاسخ دهید');
            return;
        }
        answers.push({ user_id: currentUser.id, question_id: qid, value: parseInt(value) });
    }

    try {
        showLoading();
        const response = await fetch(`${API_BASE_URL}/answers/${currentUser.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(answers)
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw errorData;
        }
        localStorage.setItem('isNewUser', 'false');
        isNewUser = false;
        navigateTo('home');
    } catch (error) {
        showError(error.detail || 'خطا در ذخیره پاسخ‌ها');
    } finally {
        hideLoading();
    }
};


// --- Profile ---

const updateProfilePage = async () => {
    if (!currentUser) return;
    try {
        showLoading();
        const [userResponse, answersResponse] = await Promise.all([
            fetch(`${API_BASE_URL}/users/${currentUser.id}`),
            fetch(`${API_BASE_URL}/answers/?user_id=${currentUser.id}`).catch(() => null)
        ]);

        if (!userResponse.ok) throw new Error('User not found');
        const user = await userResponse.json();

        const fields = {
            'profile-name': user.name || '-',
            'profile-class': user.class_name || '-',
            'profile-student-id': user.student_id || '-',
            'profile-gender': user.gender === 'male' ? 'مرد' : user.gender === 'female' ? 'زن' : '-',
            'profile-email': user.email || '-'
        };
        Object.entries(fields).forEach(([id, value]) => {
            const el = document.getElementById(id);
            if (el) el.textContent = value;
        });

        if (answersResponse && answersResponse.ok) {
            const answers = await answersResponse.json();
            const answerFields = {
                'hygiene-result': 1, 'socializing-result': 2, 'smoking-result': 3,
                'noise-result': 4, 'beliefs-result': 5, 'sleep-result': 6
            };
            Object.entries(answerFields).forEach(([id, qid]) => {
                const el = document.getElementById(id);
                if (el) el.textContent = answers.find(a => a.question_id === qid)?.value?.toString() || '-';
            });
        }
    } catch (error) {
        showError('خطا در بارگذاری پروفایل');
    } finally {
        hideLoading();
    }
};


// --- Group / Home ---

const loadGroupInfo = async () => {
    if (!currentUser) return;
    try {
        showLoading();
        const response = await fetch(`${API_BASE_URL}/group/${currentUser.id}`);
        const noGroupDiv = document.getElementById('no-group');
        const groupInfoDiv = document.getElementById('group-info');
        const groupMembersDiv = document.getElementById('group-members');
        const memberCountEl = document.getElementById('group-member-count');

        if (!response.ok) {
            // No group
            if (noGroupDiv) noGroupDiv.classList.remove('hidden');
            if (groupInfoDiv) groupInfoDiv.classList.add('hidden');
            hideLoading();
            return;
        }

        const group = await response.json();
        if (noGroupDiv) noGroupDiv.classList.add('hidden');
        if (groupInfoDiv) groupInfoDiv.classList.remove('hidden');
        if (memberCountEl) memberCountEl.textContent = group.members.length;

        if (groupMembersDiv) {
            groupMembersDiv.innerHTML = '';
            group.members.forEach(member => {
                const card = document.createElement('div');
                card.className = 'roommate-card';
                card.innerHTML = `
                    <div class="profile-container">
                        <img src="${member.user.gender === 'male' ? '../src/avatar-male.png' : '../src/avatar-female-3d.png'}" class="profile-icon" alt="آیکون" style="width: 60px; height: 60px;">
                    </div>
                    <h3 class="text-sm font-semibold text-gray-800 font-fa mt-2">${sanitizeInput(member.user.name)}</h3>
                    <p class="text-xs text-gray-600 font-fa">${sanitizeInput(member.user.class_name)}</p>
                `;
                groupMembersDiv.appendChild(card);
            });
        }
    } catch (error) {
        showError('خطا در بارگذاری گروه');
    } finally {
        hideLoading();
    }
};


// --- Matches ---

const displaySuggestedRoommates = async () => {
    if (!currentUser) return;
    showLoading();
    try {
        const response = await fetch(`${API_BASE_URL}/matches/${currentUser.id}`);
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Failed');
        }
        const matches = await response.json();
        const container = document.getElementById('suggested-roommates');
        if (!container) { hideLoading(); return; }
        container.innerHTML = '';

        if (matches.length === 0) {
            container.innerHTML = '<p class="text-center text-gray-600 font-fa col-span-2">هیچ هم‌اتاقی پیشنهادی یافت نشد</p>';
            hideLoading();
            return;
        }

        matches.forEach(match => {
            const user = match.user;
            const card = document.createElement('div');
            card.className = 'roommate-card cursor-pointer';
            card.addEventListener('click', () => viewRoommateProfile(user.id, match.match_percentage));
            card.innerHTML = `
                <div class="profile-container">
                    <svg class="progress-circle" viewBox="0 0 100 100">
                        <circle cx="50" cy="50" r="40" fill="none" stroke="#e5e7eb" stroke-width="10"/>
                        <circle cx="50" cy="50" r="40" fill="none" stroke="#3b82f6" stroke-width="10" stroke-dasharray="${match.match_percentage * 2.51}, 251.2"/>
                    </svg>
                    <img src="${user.gender === 'male' ? '../src/avatar-male.png' : '../src/avatar-female-3d.png'}" class="profile-icon" alt="آیکون" style="width: 75px; height: 75px;">
                    <span class="match-percentage">${match.match_percentage}%</span>
                </div>
                <h3 class="text-sm font-semibold text-gray-800 font-fa mt-4">${sanitizeInput(user.name)}</h3>
                <p class="text-xs text-gray-600 font-fa">${sanitizeInput(user.class_name)}</p>
            `;
            container.appendChild(card);
        });
    } catch (error) {
        showError(error.message || 'خطا در بارگذاری مچ‌ها');
    } finally {
        hideLoading();
    }
};


// --- Roommate Profile ---

const viewRoommateProfile = async (roommateId, matchPercentage) => {
    currentRoommateId = roommateId;
    try {
        showLoading();
        const [userResponse, answersResponse] = await Promise.all([
            fetch(`${API_BASE_URL}/users/${roommateId}`),
            fetch(`${API_BASE_URL}/answers/?user_id=${roommateId}`).catch(() => null)
        ]);

        if (!userResponse.ok) throw new Error('User not found');
        const roommate = await userResponse.json();

        const fields = {
            'roommate-name': roommate.name || '-',
            'roommate-description': roommate.class_name || '-'
        };
        Object.entries(fields).forEach(([id, value]) => {
            const el = document.getElementById(id);
            if (el) el.textContent = value;
        });

        // Match percentage
        const matchEl = document.getElementById('roommate-match-percentage');
        if (matchEl) matchEl.textContent = matchPercentage ? `${matchPercentage}%` : '-';

        if (answersResponse && answersResponse.ok) {
            const answers = await answersResponse.json();
            const answerFields = {
                'roommate-cleanliness-result': 1, 'roommate-social-result': 2,
                'roommate-smoking-result': 3, 'roommate-noise-result': 4,
                'roommate-beliefs-result': 5, 'roommate-sleep-result': 6
            };
            Object.entries(answerFields).forEach(([id, qid]) => {
                const el = document.getElementById(id);
                if (el) el.textContent = answers.find(a => a.question_id === qid)?.value?.toString() || '-';
            });
        }

        // Reset request status
        const statusText = document.getElementById('request-status-text');
        if (statusText) { statusText.classList.add('hidden'); statusText.textContent = ''; }

        navigateTo('roommate-profile');
    } catch (error) {
        showError('خطا در بارگذاری پروفایل');
    } finally {
        hideLoading();
    }
};


// --- Requests ---

const sendRequest = async () => {
    if (!currentUser || !currentRoommateId) return;
    try {
        showLoading();
        const response = await fetch(`${API_BASE_URL}/requests/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sender_id: currentUser.id, receiver_id: currentRoommateId })
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Failed');
        }
        const statusText = document.getElementById('request-status-text');
        if (statusText) {
            statusText.textContent = 'درخواست ارسال شد!';
            statusText.classList.remove('hidden');
            statusText.classList.add('text-green-600');
        }
    } catch (error) {
        showError(error.message);
    } finally {
        hideLoading();
    }
};

const loadRequests = async () => {
    if (!currentUser) return;
    showLoading();
    try {
        const [sentRes, receivedRes] = await Promise.all([
            fetch(`${API_BASE_URL}/requests/sent/${currentUser.id}`),
            fetch(`${API_BASE_URL}/requests/received/${currentUser.id}`)
        ]);

        const sentRequests = sentRes.ok ? await sentRes.json() : [];
        const receivedRequests = receivedRes.ok ? await receivedRes.json() : [];

        // Received
        const receivedDiv = document.getElementById('received-requests');
        if (receivedDiv) {
            receivedDiv.innerHTML = '';
            if (receivedRequests.length === 0) {
                receivedDiv.innerHTML = '<p class="text-center text-gray-500 font-fa">درخواستی دریافت نشده</p>';
            } else {
                receivedRequests.forEach(req => {
                    const card = document.createElement('div');
                    card.className = 'bg-white p-4 rounded-lg shadow';
                    const statusColor = req.status === 'pending' ? 'text-yellow-600' : req.status === 'accepted' ? 'text-green-600' : 'text-red-600';
                    const statusText = req.status === 'pending' ? 'در انتظار' : req.status === 'accepted' ? 'تأیید شده' : 'رد شده';

                    card.innerHTML = `
                        <div class="flex justify-between items-center">
                            <div>
                                <p class="font-semibold font-fa">${sanitizeInput(req.sender.name)}</p>
                                <p class="text-xs text-gray-500 font-fa">${sanitizeInput(req.sender.class_name)}</p>
                            </div>
                            <span class="text-sm font-fa ${statusColor}">${statusText}</span>
                        </div>
                        ${req.status === 'pending' ? `
                            <div class="flex gap-2 mt-3">
                                <button onclick="acceptRequest(${req.id})" class="flex-1 bg-green-500 text-white p-2 rounded-lg hover:bg-green-600 font-fa text-sm">تأیید</button>
                                <button onclick="rejectRequest(${req.id})" class="flex-1 bg-red-500 text-white p-2 rounded-lg hover:bg-red-600 font-fa text-sm">رد</button>
                            </div>
                        ` : ''}
                    `;
                    receivedDiv.appendChild(card);
                });
            }
        }

        // Sent
        const sentDiv = document.getElementById('sent-requests');
        if (sentDiv) {
            sentDiv.innerHTML = '';
            if (sentRequests.length === 0) {
                sentDiv.innerHTML = '<p class="text-center text-gray-500 font-fa">درخواستی ارسال نشده</p>';
            } else {
                sentRequests.forEach(req => {
                    const card = document.createElement('div');
                    card.className = 'bg-white p-4 rounded-lg shadow';
                    const statusColor = req.status === 'pending' ? 'text-yellow-600' : req.status === 'accepted' ? 'text-green-600' : 'text-red-600';
                    const statusText = req.status === 'pending' ? 'در انتظار' : req.status === 'accepted' ? 'تأیید شده' : 'رد شده';

                    card.innerHTML = `
                        <div class="flex justify-between items-center">
                            <div>
                                <p class="font-semibold font-fa">${sanitizeInput(req.receiver.name)}</p>
                                <p class="text-xs text-gray-500 font-fa">${sanitizeInput(req.receiver.class_name)}</p>
                            </div>
                            <span class="text-sm font-fa ${statusColor}">${statusText}</span>
                        </div>
                    `;
                    sentDiv.appendChild(card);
                });
            }
        }
    } catch (error) {
        showError('خطا در بارگذاری درخواست‌ها');
    } finally {
        hideLoading();
    }
};

const acceptRequest = async (requestId) => {
    if (!currentUser) return;
    try {
        showLoading();
        const response = await fetch(`${API_BASE_URL}/requests/${requestId}/accept?current_user_id=${currentUser.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' }
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Failed');
        }
        showError('درخواست تأیید شد!');
        loadRequests();
        loadGroupInfo();
    } catch (error) {
        showError(error.message);
    } finally {
        hideLoading();
    }
};

const rejectRequest = async (requestId) => {
    if (!currentUser) return;
    try {
        showLoading();
        const response = await fetch(`${API_BASE_URL}/requests/${requestId}/reject?current_user_id=${currentUser.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' }
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Failed');
        }
        loadRequests();
    } catch (error) {
        showError(error.message);
    } finally {
        hideLoading();
    }
};


// --- Rooms ---

const loadRooms = async () => {
    try {
        showLoading();
        const response = await fetch(`${API_BASE_URL}/rooms/`);
        if (!response.ok) throw new Error('Failed');
        const rooms = await response.json();
        const container = document.getElementById('rooms-list');
        if (!container) { hideLoading(); return; }
        container.innerHTML = '';

        if (rooms.length === 0) {
            container.innerHTML = '<p class="text-center text-gray-500 font-fa">هیچ اتاقی ثبت نشده است</p>';
            hideLoading();
            return;
        }

        rooms.forEach(room => {
            const card = document.createElement('div');
            card.className = 'bg-white p-4 rounded-lg shadow';
            const occupancyPercent = room.capacity > 0 ? (room.current_occupancy / room.capacity) * 100 : 0;
            card.innerHTML = `
                <div class="flex justify-between items-center mb-2">
                    <h3 class="font-semibold font-fa">اتاق ${sanitizeInput(room.number)}</h3>
                    <span class="text-sm text-gray-500 font-fa">${sanitizeInput(room.dormitory)}</span>
                </div>
                <div class="flex justify-between text-sm text-gray-600 font-fa mb-2">
                    <span>ظرفیت: ${room.capacity} نفره</span>
                    <span>ساکن: ${room.current_occupancy} نفر</span>
                </div>
                <div class="bg-gray-200 h-2 rounded-full">
                    <div class="bg-blue-500 h-full rounded-full" style="width: ${occupancyPercent}%"></div>
                </div>
            `;
            container.appendChild(card);
        });
    } catch (error) {
        showError('خطا در بارگذاری اتاق‌ها');
    } finally {
        hideLoading();
    }
};


// --- Init ---

document.addEventListener('DOMContentLoaded', () => {
    if (localStorage.getItem('theme') === 'dark') {
        document.body.classList.add('dark-mode');
    }

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

    const hash = window.location.hash.replace('#', '');
    const validSections = ['login', 'signup', 'quiz', 'home', 'roommates', 'requests', 'rooms', 'profile', 'roommate-profile'];

    if (validSections.includes(hash)) {
        if (['home', 'roommates', 'requests', 'rooms', 'profile', 'roommate-profile'].includes(hash) && !currentUser) {
            navigateTo('login');
        } else if (hash === 'quiz' && !isNewUser && !currentUser) {
            navigateTo('login');
        } else {
            navigateTo(hash);
        }
    } else {
        if (!currentUser) {
            navigateTo('login');
        } else if (isNewUser) {
            navigateTo('quiz');
        } else {
            navigateTo('home');
        }
    }

    renderNavigation();
});

window.addEventListener('hashchange', () => {
    const hash = window.location.hash.replace('#', '');
    const validSections = ['login', 'signup', 'quiz', 'home', 'roommates', 'requests', 'rooms', 'profile', 'roommate-profile'];

    if (validSections.includes(hash)) {
        if (['home', 'roommates', 'requests', 'rooms', 'profile', 'roommate-profile'].includes(hash) && !currentUser) {
            navigateTo('login');
        } else {
            navigateTo(hash);
        }
    } else {
        navigateTo(currentUser ? 'home' : 'login');
    }
});
