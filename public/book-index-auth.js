if (location.protocol === 'http:' || location.protocol === 'https:') {
  const showAuthError = error => {
    console.error('Unable to check sign-in status:', error);
    document.getElementById('auth-message').textContent = 'We couldn’t check your sign-in. Please try again.';
    document.getElementById('auth-retry').hidden = false;
  };
  document.getElementById('auth-retry').addEventListener('click', () => location.reload());
  try {
    const [{ initializeApp }, { getAuth, onAuthStateChanged }] = await Promise.all([
      import('https://www.gstatic.com/firebasejs/13.4.0/firebase-app.js'),
      import('https://www.gstatic.com/firebasejs/13.4.0/firebase-auth.js')
    ]);
    const app = initializeApp({
      apiKey: "AIzaSyC4ZCg4k2bnMJmwUqGefe4cX8DeHKFcFAM",
      authDomain: "bookcast-serhii.firebaseapp.com",
      projectId: "bookcast-serhii",
      storageBucket: "bookcast-serhii.firebasestorage.app",
      messagingSenderId: "367024278867",
      appId: "1:367024278867:web:42ba8c6841215113a7e5a6",
      measurementId: "G-EWG7LF2QYG"
    });
    onAuthStateChanged(getAuth(app), user => {
      if (!user) location.replace('../login.html');
      else document.documentElement.classList.remove('auth-pending');
    }, showAuthError);
  } catch (error) {
    showAuthError(error);
  }
}
