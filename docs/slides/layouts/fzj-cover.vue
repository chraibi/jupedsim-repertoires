<template>
  <div class="fzj-cover">
    <div class="hero"></div>
    <div class="band">
      <div class="band-inner">
        <slot />
      </div>
    </div>
  </div>
</template>

<style scoped>
.fzj-cover {
  width: 100%;
  height: 100%;
  background: #fff;
  position: relative;
}
.hero {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 46%;
  background: url('/cover_crowd.jpg') center 40% / cover no-repeat;
}
.band {
  position: absolute;
  top: 46%;
  left: 0;
  right: 0;
  height: 34%;
  background: #023d6b;
  color: #fff;
  display: flex;
  align-items: center;
}
.band-inner {
  padding: 0 3.2rem;
  width: 100%;
}
.band-inner :deep(h1) {
  color: #fff;
  font-weight: 700;
  text-transform: uppercase;
  font-size: 1.55rem;
  line-height: 1.12;
  margin: 0 0 0.3rem 0;
}
.band-inner :deep(h2) {
  color: #b4c3da;
  font-weight: 700;
  font-size: 1.0rem;
  margin: 0 0 0.9rem 0;
  border: none;
}
.band-inner :deep(p) {
  color: #fff;
  font-size: 0.7rem;
  margin: 0.1rem 0;
  opacity: 0.95;
}
</style>
