document.addEventListener('DOMContentLoaded', () => {

    // FAQ Toggle
    const faqItems = document.querySelectorAll('.faq-item');
    faqItems.forEach(item => {
        const header = item.querySelector('.flex');
        header.addEventListener('click', () => {
            const isActive = item.classList.contains('active');
            
            // Close all other items
            faqItems.forEach(i => {
                i.classList.remove('active');
                i.querySelector('p').style.display = 'none';
                i.querySelector('.arrow').style.transform = 'rotate(0deg)';
            });

            // Toggle current item
            if (!isActive) {
                item.classList.add('active');
                item.querySelector('p').style.display = 'block';
                item.querySelector('.arrow').style.transform = 'rotate(180deg)';
            }
        });
    });

    // Word Rotator
    const words = document.querySelectorAll('#rotator .word');
    const wordList = ["باحال", "خوش صحبت", "دانشجویی", "آروم", "تمیز", "خفن"];
    let index = 0;

    function updateWords() {
        words.forEach(word => {
            word.classList.remove('pos2', 'pos1', 'active', 'neg1', 'neg2');
            word.style.zIndex = 0;
        });

        const len = words.length;
        const pos2Index = (index - 2 + len) % len;
        const pos1Index = (index - 1 + len) % len;
        const activeIndex = index;
        const neg1Index = (index + 1) % len;
        const neg2Index = (index + 2) % len;

        words[pos2Index].classList.add('pos2');
        words[pos1Index].classList.add('pos1');
        words[activeIndex].classList.add('active');
        words[neg1Index].classList.add('neg1');
        words[neg2Index].classList.add('neg2');

        words[activeIndex].style.zIndex = 5;
        words[pos1Index].style.zIndex = 4;
        words[neg1Index].style.zIndex = 4;
        words[pos2Index].style.zIndex = 3;
        words[neg2Index].style.zIndex = 3;

        index = (index + 1) % len;
    }

    if (words.length > 0) {
        updateWords();
        setInterval(updateWords, 2000);
    } else {
        console.error('No elements with class .word found inside #rotator');
    }

     const container = document.getElementById('scrollContainer');
    const items = container.querySelectorAll('div');
    const scrollLeftBtn = document.getElementById('scrollLeft');
    const scrollRightBtn = document.getElementById('scrollRight');

    let currentIndex = 0;

    function scrollToIndex(index) {
      if (index < 0 || index >= items.length) return;
      currentIndex = index;
      const item = items[currentIndex];
      container.scrollTo({
        left: item.offsetLeft - 16, // فاصله gap
        behavior: 'smooth'
      });
    }

    scrollLeftBtn.addEventListener('click', () => {
      scrollToIndex(currentIndex - 1);
    });

    scrollRightBtn.addEventListener('click', () => {
      scrollToIndex(currentIndex + 1);
    });

    container.addEventListener('scroll', () => {
      let closestIndex = 0;
      let closestDistance = Infinity;
      items.forEach((item, index) => {
        const distance = Math.abs(item.offsetLeft - container.scrollLeft);
        if (distance < closestDistance) {
          closestDistance = distance;
          closestIndex = index;
        }
      });
      currentIndex = closestIndex;
    });
    
    // Animated Images
    document.querySelectorAll('.animated-image').forEach(img => {
        const translateX = (Math.random() - 0.5) * 10;
        const translateY = (Math.random() - 0.5) * 10;
        const rotate = (Math.random() - 0.5) * 3;
        const duration = 3 + Math.random() * 2;
        const delay = Math.random() * 1;

        img.style.setProperty('--translate-x', `${translateX}px`);
        img.style.setProperty('--translate-y', `${translateY}px`);
        img.style.setProperty('--rotate', `${rotate}deg`);
        img.style.animation = `float ${duration}s infinite ease-in-out ${delay}s`;
    });
  
});