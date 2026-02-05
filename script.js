// ===== SPLASH SCREEN =====
document.addEventListener('DOMContentLoaded', function() {
  var splash = document.getElementById('splash');
  var splashParticles = document.getElementById('splashParticles');
  var siteWrapper = document.querySelector('.site-wrapper');

  // Create floating particles for splash screen
  for (var i = 0; i < 20; i++) {
    var particle = document.createElement('div');
    particle.className = 'splash-particle';
    particle.style.left = Math.random() * 100 + '%';
    particle.style.top = Math.random() * 100 + '%';
    particle.style.animationDelay = Math.random() * 3 + 's';
    particle.style.animationDuration = (3 + Math.random() * 4) + 's';
    splashParticles.appendChild(particle);
  }

  // Start fading in main site slightly before splash fades out
  setTimeout(function() {
    siteWrapper.classList.add('visible');
  }, 2500);

  // Fade out splash screen
  setTimeout(function() {
    splash.classList.add('fade-out');
  }, 3000);

  // Remove splash screen from DOM
  setTimeout(function() {
    splash.classList.add('hidden');
  }, 4500);
});


// ===== HIGH-RES STAR FIELD =====
function initStarfield() {
  var canvas = document.getElementById('starfield');
  if (!canvas) return;

  var ctx = canvas.getContext('2d');
  var dpr = window.devicePixelRatio || 1;

  function resizeCanvas() {
    canvas.width = window.innerWidth * dpr;
    canvas.height = window.innerHeight * dpr;
    canvas.style.width = window.innerWidth + 'px';
    canvas.style.height = window.innerHeight + 'px';
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(dpr, dpr);
    drawStars();
  }

  function drawStars() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    var width = window.innerWidth;
    var height = window.innerHeight;

    // Layer 1: Distant tiny stars
    for (var i = 0; i < 2000; i++) {
      var x = Math.random() * width;
      var y = Math.random() * height;
      var radius = Math.random() * 0.5 + 0.1;
      var opacity = Math.random() * 0.5 + 0.2;

      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255, 255, 255, ' + opacity + ')';
      ctx.fill();
    }

    // Layer 2: Medium stars with color variation
    var colors = [
      'rgba(255, 255, 255, ',
      'rgba(200, 220, 255, ',
      'rgba(255, 250, 240, ',
      'rgba(255, 240, 220, '
    ];

    for (var i = 0; i < 500; i++) {
      var x = Math.random() * width;
      var y = Math.random() * height;
      var radius = Math.random() * 0.8 + 0.3;
      var opacity = Math.random() * 0.4 + 0.4;
      var colorBase = colors[Math.floor(Math.random() * colors.length)];

      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fillStyle = colorBase + opacity + ')';
      ctx.fill();
    }

    // Layer 3: Bright stars with glow
    for (var i = 0; i < 100; i++) {
      var x = Math.random() * width;
      var y = Math.random() * height;
      var radius = Math.random() * 1.2 + 0.5;

      var gradient = ctx.createRadialGradient(x, y, 0, x, y, radius * 4);
      gradient.addColorStop(0, 'rgba(255, 255, 255, 0.9)');
      gradient.addColorStop(0.1, 'rgba(255, 255, 255, 0.5)');
      gradient.addColorStop(0.5, 'rgba(200, 220, 255, 0.1)');
      gradient.addColorStop(1, 'transparent');

      ctx.beginPath();
      ctx.arc(x, y, radius * 4, 0, Math.PI * 2);
      ctx.fillStyle = gradient;
      ctx.fill();

      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255, 255, 255, 1)';
      ctx.fill();
    }

    // Layer 4: Feature stars with cross flare
    for (var i = 0; i < 15; i++) {
      var x = Math.random() * width;
      var y = Math.random() * height;
      var size = Math.random() * 2 + 1;

      // Horizontal flare
      var hGradient = ctx.createLinearGradient(x - size * 8, y, x + size * 8, y);
      hGradient.addColorStop(0, 'transparent');
      hGradient.addColorStop(0.4, 'rgba(255, 255, 255, 0.1)');
      hGradient.addColorStop(0.5, 'rgba(255, 255, 255, 0.4)');
      hGradient.addColorStop(0.6, 'rgba(255, 255, 255, 0.1)');
      hGradient.addColorStop(1, 'transparent');

      ctx.beginPath();
      ctx.rect(x - size * 8, y - 0.5, size * 16, 1);
      ctx.fillStyle = hGradient;
      ctx.fill();

      // Vertical flare
      var vGradient = ctx.createLinearGradient(x, y - size * 8, x, y + size * 8);
      vGradient.addColorStop(0, 'transparent');
      vGradient.addColorStop(0.4, 'rgba(255, 255, 255, 0.1)');
      vGradient.addColorStop(0.5, 'rgba(255, 255, 255, 0.4)');
      vGradient.addColorStop(0.6, 'rgba(255, 255, 255, 0.1)');
      vGradient.addColorStop(1, 'transparent');

      ctx.beginPath();
      ctx.rect(x - 0.5, y - size * 8, 1, size * 16);
      ctx.fillStyle = vGradient;
      ctx.fill();

      // Glow
      var gradient = ctx.createRadialGradient(x, y, 0, x, y, size * 6);
      gradient.addColorStop(0, 'rgba(255, 255, 255, 1)');
      gradient.addColorStop(0.15, 'rgba(255, 255, 255, 0.6)');
      gradient.addColorStop(0.4, 'rgba(200, 220, 255, 0.2)');
      gradient.addColorStop(1, 'transparent');

      ctx.beginPath();
      ctx.arc(x, y, size * 6, 0, Math.PI * 2);
      ctx.fillStyle = gradient;
      ctx.fill();

      // Bright core
      ctx.beginPath();
      ctx.arc(x, y, size, 0, Math.PI * 2);
      ctx.fillStyle = 'white';
      ctx.fill();
    }
  }

  resizeCanvas();
  window.addEventListener('resize', resizeCanvas);
}

document.addEventListener('DOMContentLoaded', initStarfield);


// ===== MOBILE MENU =====
document.addEventListener('DOMContentLoaded', function() {
  var mobileMenuBtn = document.getElementById('mobileMenuBtn');
  var mobileMenu = document.getElementById('mobileMenu');

  if (mobileMenuBtn && mobileMenu) {
    mobileMenuBtn.addEventListener('click', function() {
      mobileMenu.classList.toggle('open');
    });

    var mobileLinks = mobileMenu.querySelectorAll('a');
    mobileLinks.forEach(function(link) {
      link.addEventListener('click', function() {
        mobileMenu.classList.remove('open');
      });
    });
  }
});


// ===== SMOOTH SCROLL =====
document.addEventListener('DOMContentLoaded', function() {
  var links = document.querySelectorAll('a[href^="#"]');

  links.forEach(function(link) {
    link.addEventListener('click', function(e) {
      var href = this.getAttribute('href');
      if (href === '#') return;

      var target = document.querySelector(href);
      if (target) {
        e.preventDefault();
        target.scrollIntoView({
          behavior: 'smooth',
          block: 'start'
        });
      }
    });
  });
});


// ===== PROJECT CARD HOVER =====
document.addEventListener('DOMContentLoaded', function() {
  var cards = document.querySelectorAll('.project-card');

  cards.forEach(function(card) {
    card.addEventListener('mouseenter', function() {
      this.style.transform = 'translateY(-4px)';
    });
    card.addEventListener('mouseleave', function() {
      this.style.transform = 'translateY(0)';
    });
  });
});


// ===== INTERSECTION OBSERVER =====
document.addEventListener('DOMContentLoaded', function() {
  var observer = new IntersectionObserver(function(entries) {
    entries.forEach(function(entry) {
      if (entry.isIntersecting) {
        entry.target.classList.add('animate-in');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1 });

  var elements = document.querySelectorAll('.about-card, .project-card, .families-aside, .principle-card');
  elements.forEach(function(el) {
    observer.observe(el);
  });
});
