<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const canvasRef = ref<HTMLCanvasElement>()
let ctx: CanvasRenderingContext2D | null = null
let animationId = 0
let particles: Particle[] = []
const mouse = ref({ x: 0, y: 0 })
interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  size: number
  color: string
  opacity: number
}

function initCanvas() {
  if (!canvasRef.value) return
  const canvas = canvasRef.value
  const dpr = window.devicePixelRatio || 1
  canvas.width = window.innerWidth * dpr
  canvas.height = window.innerHeight * dpr
  ctx = canvas.getContext('2d')
  if (ctx) {
    ctx.scale(dpr, dpr)
    canvas.style.width = `${window.innerWidth}px`
    canvas.style.height = `${window.innerHeight}px`
  }
}

function createParticles() {
  particles = []
  const count = Math.min(80, Math.floor((window.innerWidth * window.innerHeight) / 18000))
  for (let i = 0; i < count; i++) {
    const type = Math.random()
    let color: string
    if (type > 0.6) color = 'rgba(240,176,32,'
    else if (type > 0.3) color = 'rgba(0,212,255,'
    else color = 'rgba(200,210,230,'

    particles.push({
      x: Math.random() * window.innerWidth,
      y: Math.random() * window.innerHeight,
      vx: (Math.random() - 0.5) * 0.4,
      vy: (Math.random() - 0.5) * 0.4,
      size: Math.random() * 2 + 0.5,
      color,
      opacity: Math.random() * 0.6 + 0.2,
    })
  }
}

function animate() {
  if (!ctx || !canvasRef.value) return
  const w = window.innerWidth
  const h = window.innerHeight
  ctx.clearRect(0, 0, w, h)

  // 绘制连线
  for (let i = 0; i < particles.length; i++) {
    for (let j = i + 1; j < particles.length; j++) {
      const dx = particles[i].x - particles[j].x
      const dy = particles[i].y - particles[j].y
      const dist = Math.sqrt(dx * dx + dy * dy)
      if (dist < 140) {
        const opacity = ((1 - dist / 140) * 0.1)
        ctx.beginPath()
        ctx.strokeStyle = `rgba(240,176,32,${opacity})`
        ctx.lineWidth = 0.5
        ctx.moveTo(particles[i].x, particles[i].y)
        ctx.lineTo(particles[j].x, particles[j].y)
        ctx.stroke()
      }
    }
  }

  // 更新和绘制粒子
  for (const p of particles) {
    p.x += p.vx
    p.y += p.vy
    if (p.x < 0 || p.x > w) p.vx *= -1
    if (p.y < 0 || p.y > h) p.vy *= -1

    ctx.beginPath()
    ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2)
    ctx.fillStyle = p.color + p.opacity + ')'
    ctx.fill()
  }

  animationId = requestAnimationFrame(animate)
}

function handleMouseMove(e: MouseEvent) {
  mouse.value.x = e.clientX
  mouse.value.y = e.clientY
}

onMounted(() => {
  initCanvas()
  createParticles()
  animate()
  window.addEventListener('resize', () => { initCanvas(); createParticles() })
  window.addEventListener('mousemove', handleMouseMove)
})

onUnmounted(() => {
  cancelAnimationFrame(animationId)
  window.removeEventListener('resize', initCanvas)
})
</script>

<template>
  <div class="fixed inset-0 z-0 pointer-events-none overflow-hidden">
    <!-- 渐变基底 -->
    <div class="absolute inset-0 bg-gradient-to-b from-surface-deep via-surface to-surface-deep" />

    <!-- 网格 -->
    <div class="absolute inset-0 bg-grid-pattern bg-grid opacity-40" style="mask-image: radial-gradient(ellipse at center, black 30%, transparent 70%)" />

    <!-- 扫描线 -->
    <div class="absolute inset-0 overflow-hidden">
      <div class="absolute w-full h-[200px] opacity-[0.02] bg-gradient-to-b from-transparent via-gold-400/20 to-transparent animate-scan" />
    </div>

    <!-- 浮动光球 -->
    <div class="absolute w-[400px] h-[400px] rounded-full blur-[80px] opacity-60 top-[10%] left-[-5%]
                bg-gold-400/10 animate-float" style="animation-duration:12s" />
    <div class="absolute w-[350px] h-[350px] rounded-full blur-[80px] opacity-50 bottom-[10%] right-[-5%]
                bg-cyan-400/8 animate-float" style="animation-delay:-4s;animation-duration:14s" />
    <div class="absolute w-[280px] h-[280px] rounded-full blur-[80px] opacity-40 top-[55%] left-[45%]
                bg-pink-500/5 animate-float" style="animation-delay:-8s;animation-duration:18s" />

    <!-- 角落光效 -->
    <div class="absolute top-0 left-0 w-[500px] h-[500px]
                bg-radial-gradient from-gold-400/5 to-transparent" />
    <div class="absolute bottom-0 right-0 w-[600px] h-[600px]
                bg-radial-gradient from-cyan-400/4 to-transparent" />

    <!-- 粒子 Canvas -->
    <canvas ref="canvasRef" class="absolute inset-0 w-full h-full" />
  </div>
</template>