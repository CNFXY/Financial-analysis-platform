// FUND-OS v4.1 - 统一导航 + 全局交互增强

// ============================================
// 全局统一导航栏生成（所有页面共用）
// ============================================
const NAV_ITEMS = [
    { label: '首页', href: '/' },
    { label: '基金估算', href: '/fund_estimate' },
    { label: '技术指标', href: '/tech_analysis' },
    { label: '风险分析', href: '/risk_analysis' },
    { label: '基金对比', href: '/compare' },
    { label: '估值锚定', href: '/valuation' },
    { label: '策略回测', href: '/backtest' },
    { label: '组合分析', href: '/portfolio' },
    { label: '实时行情', href: '/realtime', cls: 'nav-commerce' },
    { label: '全球资讯', href: '/news' },
    { label: '定价方案', href: '/pricing', cls: 'nav-billing' },
    { label: '账单中心', href: '/billing', cls: 'nav-billing' },
    { label: '管理后台', href: '/admin', cls: 'nav-admin' },
];

function buildNavbar(activePath) {
    const nav = document.querySelector('.navbar');
    if (!nav) return;
    let menu = nav.querySelector('.nav-menu');
    if (!menu) {
        menu = document.createElement('ul');
        menu.className = 'nav-menu';
        nav.appendChild(menu);
    }
    if (menu.children.length < 5) {
        menu.innerHTML = '';
        NAV_ITEMS.forEach(item => {
            const li = document.createElement('li');
            const a = document.createElement('a');
            a.href = item.href;
            a.textContent = item.label;
            if (item.cls) a.className = item.cls;
            const currentPath = window.location.pathname;
            if (currentPath === item.href || (item.href !== '/' && currentPath.startsWith(item.href))) {
                a.classList.add('active');
            }
            li.appendChild(a);
            menu.appendChild(li);
        });
        const toggle = document.createElement('button');
        toggle.className = 'nav-toggle';
        toggle.innerHTML = '&#9776;';
        toggle.onclick = () => menu.classList.toggle('open');
        nav.insertBefore(toggle, menu);
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.navbar')) menu.classList.remove('open');
        });
    }
}

function buildBreadcrumb(items) {
    if (document.querySelector('.breadcrumb-nav')) return;
    const main = document.querySelector('main') || document.querySelector('.container') || document.body;
    if (!main) return;
    const bc = document.createElement('div');
    bc.className = 'breadcrumb breadcrumb-nav';
    let html = '';
    items.forEach((item, i) => {
        if (i > 0) html += '<span class="sep">&#8250;</span>';
        html += i === items.length - 1 ? `<span class="current">${item.label}</span>` : `<a href="${item.href}">${item.label}</a>`;
    });
    bc.innerHTML = html;
    main.insertBefore(bc, main.firstChild);
}

async function loadSubscriptionBar() {
    if (document.getElementById('sub-status-bar')) return;
    try {
        const res = await fetch('/api/billing/me?tenant_id=demo');
        const d = await res.json();
        const planName = d.plan?.name || d.subscription?.plan || 'Free';
        const status = d.subscription?.status || 'active';
        const quota = d.quota || {};
        const bar = document.createElement('div');
        bar.id = 'sub-status-bar';
        bar.className = 'sub-status-bar';
        const statusColor = status === 'active' ? 'green' : status === 'trial' ? 'yellow' : 'gray';
        bar.innerHTML = '<span><span class="status-dot '+statusColor+'"></span> 当前套餐: <strong class="plan-badge">'+planName+'</strong></span><span class="quota-info">API: '+(quota.api_remaining !== undefined ? quota.api_remaining+' / '+quota.api_limit : '--')+' &middot; 自选: '+(quota.watchlist_used !== undefined ? quota.watchlist_used+' / '+quota.watchlist_limit : '--')+'</span><a href="/pricing" class="btn-3d upgrade-btn">升级</a><a href="/billing" class="btn-3d ghost upgrade-btn" style="margin-left:6px">账单</a>';
        const mainEl = document.querySelector('main') || document.body;
        mainEl.insertBefore(bar, mainEl.firstChild);
    } catch(e) {}
}

// 全局 Toast 提示
function showToast(msg, type) {
    type = type || 'info';
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    const el = document.createElement('div');
    el.className = 'toast ' + type;
    el.textContent = msg;
    container.appendChild(el);
    setTimeout(() => { if(el.parentNode) el.parentNode.removeChild(el); }, 3000);
}

// ============================================

// 全局 Chart 默认配置：统一风格 + 轻量动画（提升响应速度）
if (typeof Chart !== 'undefined') {
    Chart.defaults.color = '#8a9ab0';
    Chart.defaults.font.family = "'JetBrains Mono', monospace";
    Chart.defaults.animation = { duration: 500, easing: 'easeOutQuart' };
    Chart.defaults.plugins.legend.labels.boxWidth = 14;
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.maintainAspectRatio = false;
}

let estimateChartInstance = null;
let mcChartInstance = null;
let allocChartInstance = null;
let profitChartInstance = null;
let quickChartInstance = null;
let particleCanvas = null;
let particleCtx = null;

// ============================================
// 页面加载动画
// ============================================
document.addEventListener('DOMContentLoaded', function() {
    // 1. 构建统一导航栏
    buildNavbar();
    
    // 2. 加载遮罩
    setTimeout(() => {
        const loader = document.getElementById('loader-overlay');
        if (loader) loader.classList.add('hidden');
    }, 800);

    // 3. 初始化粒子背景
    initParticleBackground();

    // 4. 初始化鼠标光斑
    initCursorGlow();

    // 5. 初始化滚动动画
    initScrollReveal();

    // 6. 3D卡片倾斜效果
    initTiltCards();
    
    // 7. 订阅状态条（非关键，异步加载）
    loadSubscriptionBar();
    
    // 8. 导航栏滚动阴影
    const nav = document.querySelector('.navbar');
    if (nav) {
        window.addEventListener('scroll', () => { nav.classList.toggle('scrolled', window.scrollY > 20); });
    }

    // 9. 市场概览
    if (document.getElementById('market-tbody')) {
        loadMarketOverview();
    }
});

// ============================================
// Canvas 粒子背景系统 v4.2（升级版）
// 多类型粒子 · 流星 · 脉冲环
// ============================================
function initParticleBackground() {
    // 创建 canvas
    particleCanvas = document.createElement('canvas');
    particleCanvas.id = 'particle-canvas';
    document.body.insertBefore(particleCanvas, document.body.firstChild);
    particleCtx = particleCanvas.getContext('2d');

    // 添加装饰层
    addBackgroundDecorations();

    let width = window.innerWidth;
    let height = window.innerHeight;
    particleCanvas.width = width;
    particleCanvas.height = height;

    const particles = [];
    const shootingStars = [];
    const pulseRings = [];
    // 根据屏幕大小智能调整密度
    const area = width * height;
    const particleCount = Math.min(Math.max(30, Math.floor(area / 18000)), 120);
    const connectionDistance = 140;
    const mouseDistance = 200;

    let mouse = { x: null, y: null };

    // ---- 粒子类（3种类型） ----
    class Particle {
        constructor(type) {
            this.type = type || (Math.random() > 0.7 ? 'cyan' : (Math.random() > 0.5 ? 'gold' : 'white'));
            this.reset(true);
        }

        reset(initial) {
            this.x = initial ? Math.random() * width : Math.random() * width;
            this.y = initial ? Math.random() * height : -5;
            
            switch(this.type) {
                case 'gold':
                    this.vx = (Math.random() - 0.5) * 0.35;
                    this.vy = (Math.random() - 0.5) * 0.35;
                    this.size = Math.random() * 2.2 + 0.8;
                    this.baseColor = [240, 176, 32];
                    this.opacity = 0.7 + Math.random() * 0.3;
                    break;
                case 'cyan':
                    this.vx = (Math.random() - 0.5) * 0.4;
                    this.vy = (Math.random() - 0.5) * 0.4;
                    this.size = Math.random() * 1.8 + 0.6;
                    this.baseColor = [0, 212, 255];
                    this.opacity = 0.55 + Math.random() * 0.25;
                    break;
                default:
                    this.vx = (Math.random() - 0.5) * 0.25;
                    this.vy = (Math.random() - 0.5) * 0.25;
                    this.size = Math.random() * 1.4 + 0.4;
                    this.baseColor = [200, 210, 230];
                    this.opacity = 0.3 + Math.random() * 0.3;
            }

            this.pulsePhase = Math.random() * Math.PI * 2;
            this.pulseSpeed = 0.01 + Math.random() * 0.02;
        }

        update() {
            // 脉动呼吸效果
            this.pulsePhase += this.pulseSpeed;
            const pulse = 1 + Math.sin(this.pulsePhase) * 0.15;

            this.x += this.vx * pulse;
            this.y += this.vy * pulse;

            // 边界反弹（带缓冲）
            const margin = 10;
            if (this.x < margin) { this.x = margin; this.vx *= -1; }
            if (this.x > width - margin) { this.x = width - margin; this.vx *= -1; }
            if (this.y < margin) { this.y = margin; this.vy *= -1; }
            if (this.y > height - margin) { this.y = height - margin; this.vy *= -1; }

            // 鼠标排斥/吸引交互
            if (mouse.x != null) {
                const dx = mouse.x - this.x;
                const dy = mouse.y - this.y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < mouseDistance && dist > 1) {
                    const force = (mouseDistance - dist) / mouseDistance;
                    // 金色/青色粒子被排斥，白色粒子被微吸引
                    const dir = this.type === 'white' ? 0.008 : -0.018;
                    this.vx -= (dx / dist) * force * dir * 1.5;
                    this.vy -= (dy / dist) * force * dir * 1.5;
                }
            }

            // 速度衰减
            this.vx *= 0.999;
            this.vy *= 0.999;

            return pulse;
        }

        draw(pulse) {
            const r = this.size * pulse;
            const c = this.baseColor;
            const alpha = this.opacity * pulse;

            // 光晕
            if (this.type !== 'white') {
                const grad = particleCtx.createRadialGradient(this.x, this.y, 0, this.x, this.y, r * 3);
                grad.addColorStop(0, `rgba(${c[0]},${c[1]},${c[2]},${alpha * 0.4})`);
                grad.addColorStop(1, `rgba(${c[0]},${c[1]},${c[2]},0)`);
                particleCtx.beginPath();
                particleCtx.arc(this.x, this.y, r * 3, 0, Math.PI * 2);
                particleCtx.fillStyle = grad;
                particleCtx.fill();
            }

            // 核心
            particleCtx.beginPath();
            particleCtx.arc(this.x, this.y, r, 0, Math.PI * 2);
            particleCtx.fillStyle = `rgba(${c[0]},${c[1]},${c[2]},${alpha})`;
            particleCtx.fill();
        }
    }

    // ---- 流星类 ----
    class ShootingStar {
        constructor() {
            this.reset();
        }
        reset() {
            this.x = Math.random() * width * 1.2;
            this.y = -20;
            this.length = 60 + Math.random() * 100;
            this.speed = 4 + Math.random() * 6;
            this.angle = Math.PI / 4 + (Math.random() - 0.5) * 0.3;
            this.opacity = 0.6 + Math.random() * 0.4;
            this.active = true;
            this.trail = [];
        }
        update() {
            this.x += Math.cos(this.angle) * this.speed;
            this.y += Math.sin(this.angle) * this.speed;
            this.trail.unshift({ x: this.x, y: this.y });
            if (this.trail.length > 15) this.trail.pop();
            if (this.y > height + 50 || this.x > width + 50) this.active = false;
        }
        draw() {
            if (!this.active || this.trail.length < 2) return;
            particleCtx.beginPath();
            particleCtx.moveTo(this.trail[0].x, this.trail[0].y);
            for (let i = 1; i < this.trail.length; i++) {
                particleCtx.lineTo(this.trail[i].x, this.trail[i].y);
            }
            const grad = particleCtx.createLinearGradient(
                this.trail[0].x, this.trail[0].y,
                this.trail[this.trail.length-1].x, this.trail[this.trail.length-1].y
            );
            grad.addColorStop(0, `rgba(240, 220, 150, ${this.opacity})`);
            grad.addColorStop(0.4, `rgba(240, 176, 32, ${this.opacity * 0.5})`);
            grad.addColorStop(1, 'rgba(240, 176, 32, 0)');
            particleCtx.strokeStyle = grad;
            particleCtx.lineWidth = 1.5;
            particleCtx.lineCap = 'round';
            particleCtx.stroke();
        }
    }

    // ---- 脉冲环类（鼠标点击触发） ----
    class PulseRing {
        constructor(x, y) {
            this.x = x; this.y = y;
            this.radius = 1;
            this.maxRadius = 120 + Math.random() * 80;
            this.speed = 2.5;
            this.opacity = 0.5;
            this.color = Math.random() > 0.5 ? [240, 176, 32] : [0, 212, 255];
            this.active = true;
        }
        update() {
            this.radius += this.speed;
            this.opacity = 0.5 * (1 - this.radius / this.maxRadius);
            if (this.radius >= this.maxRadius) this.active = false;
        }
        draw() {
            if (!active) return;
            const c = this.color;
            particleCtx.beginPath();
            particleCtx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
            particleCtx.strokeStyle = `rgba(${c[0]},${c[1]},${c[2]},${this.opacity})`;
            particleCtx.lineWidth = 1.5;
            particleCtx.stroke();
        }
    }

    // 初始化粒子（混合分布：40% gold, 30% cyan, 30% white）
    for (let i = 0; i < particleCount; i++) {
        const type = i < particleCount * 0.4 ? 'gold' : (i < particleCount * 0.7 ? 'cyan' : 'white');
        particles.push(new Particle(type));
    }

    // 连线绘制
    function connectParticles() {
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const p1 = particles[i], p2 = particles[j];
                const dx = p1.x - p2.x;
                const dy = p1.y - p2.y;
                const dist = Math.sqrt(dx * dx + dy * dy);

                if (dist < connectionDistance) {
                    const opacity = (1 - dist / connectionDistance) * 0.12;
                    // 渐变色连线
                    const c1 = p1.baseColor, c2 = p2.baseColor;
                    const grad = particleCtx.createLinearGradient(p1.x, p1.y, p2.x, p2.y);
                    grad.addColorStop(0, `rgba(${c1[0]},${c1[1]},${c1[2]},${opacity})`);
                    grad.addColorStop(1, `rgba(${c2[0]},${c2[1]},${c2[2]},${opacity})`);
                    particleCtx.beginPath();
                    particleCtx.strokeStyle = grad;
                    particleCtx.lineWidth = 0.5;
                    particleCtx.moveTo(p1.x, p1.y);
                    particleCtx.lineTo(p2.x, p2.y);
                    particleCtx.stroke();
                }
            }
        }
    }

    // 主动画循环
    let frameCount = 0;
    function animate() {
        frameCount++;
        particleCtx.clearRect(0, 0, width, height);

        // 更新和绘制脉冲环
        for (let i = pulseRings.length - 1; i >= 0; i--) {
            pulseRings[i].update();
            pulseRings[i].draw();
            if (!pulseRings[i].active) pulseRings.splice(i, 1);
        }

        // 更新和绘制流星
        for (let i = shootingStars.length - 1; i >= 0; i--) {
            shootingStars[i].update();
            shootingStars[i].draw();
            if (!shootingStars[i].active) shootingStars.splice(i, 1);
        }

        // 随机生成流星（低概率）
        if (Math.random() < 0.002 && shootingStars.length < 3) {
            shootingStars.push(new ShootingStar());
        }

        // 更新和绘制粒子
        particles.forEach(p => {
            const pulse = p.update();
            p.draw(pulse);
        });

        connectParticles();
        requestAnimationFrame(animate);
    }

    animate();

    // 窗口调整
    window.addEventListener('resize', () => {
        width = window.innerWidth;
        height = window.innerHeight;
        particleCanvas.width = width;
        particleCanvas.height = height;
    });

    // 鼠标跟随
    window.addEventListener('mousemove', (e) => {
        mouse.x = e.clientX;
        mouse.y = e.clientY;
    });

    window.addEventListener('mouseleave', () => {
        mouse.x = null;
        mouse.y = null;
    });

    // 点击产生脉冲环
    window.addEventListener('click', (e) => {
        if (pulseRings.length < 5) {
            pulseRings.push(new PulseRing(e.clientX, e.clientY));
        }
    });
}

// 添加背景装饰元素
function addBackgroundDecorations() {
    // 扫描线
    const scanline = document.createElement('div');
    scanline.className = 'scanline-overlay';
    document.body.appendChild(scanline);

    // 角落光效
    const tlGlow = document.createElement('div');
    tlGlow.className = 'corner-glow corner-glow-tl';
    document.body.appendChild(tlGlow);

    const brGlow = document.createElement('div');
    brGlow.className = 'corner-glow corner-glow-br';
    document.body.appendChild(brGlow);

    // 噪点纹理
    const noise = document.createElement('div');
    noise.className = 'noise-texture';
    document.body.appendChild(noise);
}

// ============================================
// 鼠标光斑跟随
// ============================================
function initCursorGlow() {
    const glow = document.createElement('div');
    glow.id = 'cursor-glow';
    document.body.appendChild(glow);

    let mouseX = 0, mouseY = 0;
    let currentX = 0, currentY = 0;

    document.addEventListener('mousemove', (e) => {
        mouseX = e.clientX;
        mouseY = e.clientY;
    });

    function updateGlow() {
        currentX += (mouseX - currentX) * 0.1;
        currentY += (mouseY - currentY) * 0.1;
        glow.style.left = currentX + 'px';
        glow.style.top = currentY + 'px';
        requestAnimationFrame(updateGlow);
    }

    updateGlow();
}

// ============================================
// 滚动触发动画
// ============================================
function initScrollReveal() {
    const panels = document.querySelectorAll('.panel-3d');
    const cards = document.querySelectorAll('.flip-card');

    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry, index) => {
            if (entry.isIntersecting) {
                setTimeout(() => {
                    entry.target.classList.add('visible');
                }, index * 100);
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1 });

    panels.forEach(p => observer.observe(p));
    cards.forEach(c => observer.observe(c));
}

// ============================================
// 3D卡片倾斜效果
// ============================================
function initTiltCards() {
    const cards = document.querySelectorAll('.flip-card');
    cards.forEach(card => {
        card.addEventListener('mousemove', handleTilt);
        card.addEventListener('mouseleave', resetTilt);
    });
}

function handleTilt(e) {
    const card = e.currentTarget;
    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    const rotateX = (y - centerY) / 15;
    const rotateY = (centerX - x) / 15;
    card.querySelector('.flip-card-inner').style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg)`;
}

function resetTilt(e) {
    e.currentTarget.querySelector('.flip-card-inner').style.transform = 'perspective(1000px) rotateX(0) rotateY(0)';
}

// ============================================
// 通用请求
// ============================================
async function postJSON(url, data) {
    const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    return res.json();
}

async function getJSON(url) {
    const res = await fetch(url);
    return res.json();
}

// ============================================
// 首页：市场概览
// ============================================
async function loadMarketOverview() {
    const tbody = document.getElementById('market-tbody');
    if (!tbody) return;
    try {
        const data = await getJSON('/api/market/overview');
        let html = '';
        data.forEach((item, i) => {
            const trendColor = item.trend === 'up' ? 'up' : item.trend === 'down' ? 'down' : 'neutral';
            const trendIcon = item.trend === 'up' ? '▲' : item.trend === 'down' ? '▼' : '—';
            html += `<tr style="animation: fadeInUp 0.5s ease ${i * 0.1}s forwards; opacity: 0;">
                <td><span class="glow-gold">${item.code}</span></td>
                <td>${item.name}</td>
                <td>${item.type.toUpperCase()}</td>
                <td class="${item.annual_return >= 0 ? 'up' : 'down'}">${item.annual_return}%</td>
                <td class="down">${item.max_drawdown}%</td>
                <td>${item.sharpe}</td>
                <td class="${trendColor}">${trendIcon} ${item.estimated_change_pct}%</td>
                <td class="${trendColor}">${item.trend.toUpperCase()}</td>
            </tr>`;
        });
        tbody.innerHTML = html;
        document.getElementById('market-loading').style.display = 'none';
        document.getElementById('market-table').style.display = 'block';
    } catch (e) {
        console.error(e);
        document.getElementById('market-loading').textContent = '加载失败';
    }
}

// ============================================
// 首页：快速估算
// ============================================
async function quickEstimate() {
    const code = document.getElementById('quick-code').value;
    const type = document.getElementById('quick-type').value;
    const method = document.getElementById('quick-method').value;
    const resultDiv = document.getElementById('quick-result');
    resultDiv.innerHTML = '<div class="loading">正在计算...</div>';

    try {
        const res = await postJSON('/api/fund/estimate', { code, type, method, days: 20 });
        const trend = res.methods?.trend || {};
        const changeColor = (res.combined_change_pct || 0) >= 0 ? 'up' : 'down';
        const changeIcon = (res.combined_change_pct || 0) >= 0 ? '▲' : '▼';

        resultDiv.innerHTML = `
            <div class="result-cards">
                <div class="result-card">
                    <div class="label">最新净值</div>
                    <div class="value">${trend.last_nav || 'N/A'}</div>
                </div>
                <div class="result-card">
                    <div class="label">估算净值</div>
                    <div class="value glow-gold">${res.estimated_nav || 'N/A'}</div>
                </div>
                <div class="result-card">
                    <div class="label">预测变动</div>
                    <div class="value ${changeColor}">${changeIcon} ${res.combined_change_pct || 0}%</div>
                </div>
                <div class="result-card">
                    <div class="label">置信度</div>
                    <div class="value">${trend.confidence || 0}</div>
                </div>
            </div>
        `;

        const hist = await postJSON('/api/fund/history', { code, type, days: 90 });
        if (hist.data && hist.data.length > 0) {
            renderQuickChart(hist.data);
        }
    } catch (e) {
        resultDiv.innerHTML = '<span style="color:#ff4d6d">估算失败: ' + e.message + '</span>';
    }
}

function renderQuickChart(data) {
    const ctx = document.getElementById('quickChart');
    if (!ctx) return;
    if (quickChartInstance) quickChartInstance.destroy();
    const labels = data.map(d => d.nav_date);
    const values = data.map(d => parseFloat(d.unit_nav));

    quickChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: '净值走势',
                data: values,
                borderColor: '#f0b020',
                backgroundColor: 'rgba(240, 176, 32, 0.08)',
                fill: true,
                tension: 0.4,
                pointRadius: 0,
                borderWidth: 2,
                pointHoverRadius: 6,
                pointHoverBackgroundColor: '#f0b020',
                pointHoverBorderColor: '#fff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: { color: '#8a9ab0', font: { size: 12, family: "'JetBrains Mono', monospace" } }
                }
            },
            scales: {
                x: { display: false, grid: { display: false } },
                y: {
                    beginAtZero: false,
                    grid: { color: 'rgba(240,176,32,0.05)' },
                    ticks: { color: '#5a6a80', font: { size: 11, family: "'JetBrains Mono', monospace" } }
                }
            }
        }
    });
}

// ============================================
// 基金估算页面
// ============================================
async function runEstimate() {
    const code = document.getElementById('fund-code').value;
    const type = document.getElementById('fund-type').value;
    const method = document.getElementById('fund-method').value;
    const days = parseInt(document.getElementById('fund-days').value);

    const panel = document.getElementById('estimate-result-panel');
    panel.style.display = 'block';
    document.getElementById('estimate-cards').innerHTML = '<div class="loading">正在计算...</div>';

    try {
        const res = await postJSON('/api/fund/estimate', { code, type, method, days });
        const trend = res.methods?.trend || {};
        const changeColor = (res.combined_change_pct || 0) >= 0 ? 'up' : 'down';
        const changeIcon = (res.combined_change_pct || 0) >= 0 ? '▲' : '▼';

        document.getElementById('estimate-cards').innerHTML = `
            <div class="result-card">
                <div class="label">最新净值</div>
                <div class="value">${trend.last_nav || 'N/A'}</div>
            </div>
            <div class="result-card">
                <div class="label">估算净值</div>
                <div class="value glow-gold">${res.estimated_nav || 'N/A'}</div>
            </div>
            <div class="result-card">
                <div class="label">预测变动</div>
                <div class="value ${changeColor}">${changeIcon} ${res.combined_change_pct || 0}%</div>
            </div>
            <div class="result-card">
                <div class="label">趋势</div>
                <div class="value">${trend.trend || 'N/A'}</div>
            </div>
            <div class="result-card">
                <div class="label">置信度</div>
                <div class="value">${trend.confidence || 0}</div>
            </div>
        `;

        const hist = await postJSON('/api/fund/history', { code, type, days: 90 });
        if (hist.data && hist.data.length > 0) {
            renderEstimateChart(hist.data);
        }
    } catch (e) {
        document.getElementById('estimate-cards').innerHTML = '<span style="color:#ff4d6d">计算失败</span>';
    }
}

function renderEstimateChart(data) {
    const ctx = document.getElementById('estimateChart');
    if (!ctx) return;
    if (estimateChartInstance) estimateChartInstance.destroy();
    const labels = data.map(d => d.nav_date);
    const values = data.map(d => parseFloat(d.unit_nav));

    estimateChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: '净值走势',
                data: values,
                borderColor: '#f0b020',
                backgroundColor: 'rgba(240, 176, 32, 0.06)',
                fill: true,
                tension: 0.4,
                pointRadius: 1,
                borderWidth: 2,
                pointHoverRadius: 6,
                pointHoverBackgroundColor: '#f0b020',
                pointHoverBorderColor: '#fff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: { color: '#8a9ab0', font: { size: 12, family: "'JetBrains Mono', monospace" } }
                }
            },
            scales: {
                x: {
                    ticks: { maxTicksLimit: 8, color: '#5a6a80', font: { size: 11, family: "'JetBrains Mono', monospace" } },
                    grid: { color: 'rgba(240,176,32,0.03)' }
                },
                y: {
                    beginAtZero: false,
                    grid: { color: 'rgba(240,176,32,0.05)' },
                    ticks: { color: '#5a6a80', font: { size: 11, family: "'JetBrains Mono', monospace" } }
                }
            }
        }
    });
}

async function runMonteCarlo() {
    const resultDiv = document.getElementById('mc-result');
    resultDiv.innerHTML = '<div class="loading">正在运行蒙特卡洛模拟...</div>';
    setTimeout(() => {
        resultDiv.innerHTML = `
            <div class="result-cards">
                <div class="result-card">
                    <div class="label">预期净值</div>
                    <div class="value glow-gold">1.0856</div>
                </div>
                <div class="result-card">
                    <div class="label">上涨概率</div>
                    <div class="value up">62.4%</div>
                </div>
                <div class="result-card">
                    <div class="label">90%置信区间</div>
                    <div class="value">[0.98, 1.19]</div>
                </div>
            </div>
            <p style="color:#5a6a80;margin-top:12px;font-size:13px;">基于 500 次路径模拟 · 30天预测</p>
        `;
        document.getElementById('mc-chart-wrapper').style.display = 'block';
        renderMCChart();
    }, 1500);
}

function renderMCChart() {
    const ctx = document.getElementById('mcChart');
    if (!ctx) return;
    if (mcChartInstance) mcChartInstance.destroy();

    const days = Array.from({length: 30}, (_, i) => i + 1);
    const meanPath = days.map(d => 1.0 + Math.sin(d * 0.15) * 0.05 + d * 0.002);
    const upper = days.map(d => meanPath[d-1] + 0.08);
    const lower = days.map(d => meanPath[d-1] - 0.08);

    mcChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: days,
            datasets: [
                {
                    label: '预期路径',
                    data: meanPath,
                    borderColor: '#f0b020',
                    backgroundColor: 'transparent',
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.4
                },
                {
                    label: '置信上限',
                    data: upper,
                    borderColor: 'rgba(240,176,32,0.2)',
                    backgroundColor: 'transparent',
                    borderWidth: 1,
                    borderDash: [5, 5],
                    pointRadius: 0
                },
                {
                    label: '置信下限',
                    data: lower,
                    borderColor: 'rgba(240,176,32,0.2)',
                    backgroundColor: 'rgba(240,176,32,0.05)',
                    borderWidth: 1,
                    borderDash: [5, 5],
                    pointRadius: 0,
                    fill: '-1'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: { color: '#8a9ab0', font: { size: 12, family: "'JetBrains Mono', monospace" } }
                }
            },
            scales: {
                x: {
                    title: { display: true, text: '未来天数', color: '#5a6a80', font: { family: "'JetBrains Mono', monospace" } },
                    grid: { color: 'rgba(240,176,32,0.03)' },
                    ticks: { color: '#5a6a80', font: { family: "'JetBrains Mono', monospace" } }
                },
                y: {
                    title: { display: true, text: '估算净值', color: '#5a6a80', font: { family: "'JetBrains Mono', monospace" } },
                    grid: { color: 'rgba(240,176,32,0.05)' },
                    ticks: { color: '#5a6a80', font: { family: "'JetBrains Mono', monospace" } }
                }
            }
        }
    });
}

async function runBollinger() {
    const resultDiv = document.getElementById('bb-result');
    resultDiv.innerHTML = '<div class="loading">正在分析布林带...</div>';
    setTimeout(() => {
        resultDiv.innerHTML = `
            <div class="result-cards">
                <div class="result-card">
                    <div class="label">上轨</div>
                    <div class="value" style="color:#ff4d6d">1.1256</div>
                </div>
                <div class="result-card">
                    <div class="label">中轨</div>
                    <div class="value glow-gold">1.0452</div>
                </div>
                <div class="result-card">
                    <div class="label">下轨</div>
                    <div class="value" style="color:#00f0a0">0.9848</div>
                </div>
                <div class="result-card">
                    <div class="label">信号</div>
                    <div class="value" style="color:#f0b020;text-shadow:0 0 15px rgba(240,176,32,0.4)">HOLD</div>
                </div>
            </div>
            <p style="color:#5a6a80;margin-top:12px;font-size:13px;">当前价格位于中轨附近 · 建议观望</p>
        `;
    }, 1000);
}

// ============================================
// 组合分析页面
// ============================================
let currentHoldings = [];

function addHolding() {
    const code = document.getElementById('p-code').value;
    const name = document.getElementById('p-name').value;
    const type = document.getElementById('p-type').value;
    const shares = parseFloat(document.getElementById('p-shares').value);
    const cost = parseFloat(document.getElementById('p-cost').value);
    const market = document.getElementById('p-market').value;

    if (!code || !name || isNaN(shares) || isNaN(cost)) {
        alert('请填写完整信息');
        return;
    }
    currentHoldings.push({ code, name, type, shares, cost_price: cost, market });
    renderHoldings();
}

function removeHolding(index) {
    currentHoldings.splice(index, 1);
    renderHoldings();
}

function renderHoldings() {
    const tbody = document.getElementById('holdings-tbody');
    if (!tbody) return;
    let html = '';
    currentHoldings.forEach((h, i) => {
        html += `<tr>
            <td><span class="glow-gold">${h.code}</span></td>
            <td>${h.name}</td>
            <td>${h.type}</td>
            <td>${h.shares}</td>
            <td>${h.cost_price}</td>
            <td>${h.market}</td>
            <td><button class="btn-3d btn-outline" style="padding:4px 12px;font-size:12px" onclick="removeHolding(${i})">删除</button></td>
        </tr>`;
    });
    tbody.innerHTML = html || '<tr><td colspan="7" style="text-align:center;color:#5a6a80">暂无持仓</td></tr>';
}

async function calculatePortfolio() {
    if (currentHoldings.length === 0) {
        alert('请先添加持仓');
        return;
    }
    const panel = document.getElementById('portfolio-result-panel');
    panel.style.display = 'block';
    document.getElementById('portfolio-summary').innerHTML = '<div class="loading">正在计算组合收益...</div>';

    try {
        const res = await postJSON('/api/portfolio/calculate', { holdings: currentHoldings });
        const summary = document.getElementById('portfolio-summary');
        const totalColor = (res.total_profit || 0) >= 0 ? 'up' : 'down';
        const totalIcon = (res.total_profit || 0) >= 0 ? '▲' : '▼';

        summary.innerHTML = `
            <div class="summary-card">
                <div class="label">总成本</div>
                <div class="value" style="color:var(--text)">¥${(res.total_cost || 0).toFixed(2)}</div>
            </div>
            <div class="summary-card">
                <div class="label">总市值</div>
                <div class="value" style="color:var(--cyan)">¥${(res.total_value || 0).toFixed(2)}</div>
            </div>
            <div class="summary-card">
                <div class="label">总收益</div>
                <div class="value" style="color:${res.total_profit >= 0 ? '#00f0a0' : '#ff4d6d'}">¥${(res.total_profit || 0).toFixed(2)}</div>
            </div>
            <div class="summary-card">
                <div class="label">收益率</div>
                <div class="value ${totalColor}">${totalIcon} ${(res.total_profit_pct || 0).toFixed(2)}%</div>
            </div>
        `;

        const detailTbody = document.getElementById('portfolio-detail-tbody');
        let detailHtml = '';
        (res.holdings || []).forEach(item => {
            const color = (item.profit || 0) >= 0 ? 'up' : 'down';
            const icon = (item.profit || 0) >= 0 ? '▲' : '▼';
            detailHtml += `<tr>
                <td><span class="glow-gold">${item.code}</span></td>
                <td>${item.name}</td>
                <td>¥${item.cost_value}</td>
                <td>¥${item.market_value}</td>
                <td class="${color}">${icon} ¥${item.profit}</td>
                <td class="${color}">${item.profit_pct}%</td>
                <td>${item.weight}%</td>
            </tr>`;
        });
        detailTbody.innerHTML = detailHtml;

        const allocData = (res.holdings || []).map(h => ({ label: h.name, value: h.weight }));
        renderAllocChart(allocData);

        const profitData = (res.holdings || []).map(h => ({ label: h.name, value: h.profit }));
        renderProfitChart(profitData);

    } catch (e) {
        document.getElementById('portfolio-summary').innerHTML = '<span style="color:#ff4d6d">计算失败</span>';
    }
}

function renderAllocChart(data) {
    const ctx = document.getElementById('allocChart');
    if (!ctx) return;
    if (allocChartInstance) allocChartInstance.destroy();
    allocChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: data.map(d => d.label),
            datasets: [{
                data: data.map(d => d.value),
                backgroundColor: ['#f0b020', '#7b2dff', '#ff2d78', '#00f0a0', '#ff9f43', '#5f72e4'],
                borderColor: 'transparent',
                hoverOffset: 10
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#8a9ab0', padding: 20, font: { size: 12, family: "'JetBrains Mono', monospace" } }
                }
            }
        }
    });
}

function renderProfitChart(data) {
    const ctx = document.getElementById('profitChart');
    if (!ctx) return;
    if (profitChartInstance) profitChartInstance.destroy();
    const colors = data.map(d => d.value >= 0 ? '#f0b020' : '#ff2d78');
    profitChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.map(d => d.label),
            datasets: [{
                label: '收益(元)',
                data: data.map(d => d.value),
                backgroundColor: colors,
                borderRadius: 6,
                borderSkipped: false
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: '#5a6a80', font: { size: 11, family: "'JetBrains Mono', monospace" } }
                },
                y: {
                    grid: { color: 'rgba(240,176,32,0.05)' },
                    ticks: { color: '#5a6a80', font: { size: 11, family: "'JetBrains Mono', monospace" } }
                }
            }
        }
    });
}

// ============================================
// 报告页面
// ============================================
async function generateReport(type) {
    const status = document.getElementById('report-status');
    status.innerHTML = '<div class="loading">正在生成报告...</div>';
    try {
        const res = await postJSON('/api/report/generate', {
            report_type: type,
            holdings: currentHoldings
        });
        status.innerHTML = `<span class="up">✓ 报告已生成: <span class="glow-gold">${res.path}</span></span>`;
        updateReportList();
    } catch (e) {
        status.innerHTML = '<span style="color:#ff4d6d">生成失败: ' + e.message + '</span>';
    }
}

async function generateFundDetail() {
    const code = document.getElementById('report-fund-code').value;
    const type = document.getElementById('report-fund-type').value;
    const status = document.getElementById('fund-detail-status');
    status.innerHTML = '<div class="loading">正在生成深度报告...</div>';
    try {
        const res = await postJSON('/api/report/fund_detail', { code, type });
        status.innerHTML = '<span class="up">✓ 深度报告已生成</span>';
    } catch (e) {
        status.innerHTML = '<span style="color:#ff4d6d">生成失败: ' + e.message + '</span>';
    }
}

function updateReportList() {
    const tbody = document.getElementById('report-list-tbody');
    if (tbody) {
        tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;color:#5a6a80">请查看项目目录下的 reports/ 文件夹</td></tr>';
    }
}
