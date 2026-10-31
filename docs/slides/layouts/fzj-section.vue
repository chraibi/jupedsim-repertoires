<template>
  <div class="fzj-section">
    <div class="band">
      <div class="band-inner">
        <slot />
      </div>
    </div>
  </div>
</template>

<style scoped>
.fzj-section {
  width: 100%;
  height: 100%;
  background: #fff;
  position: relative;
}
.band {
  position: absolute;
  top: 5%;
  left: 0;
  right: 0;
  height: 74%;
  background: #023d6b;
  color: #fff;
  display: flex;
  align-items: center;
}
.band-inner {
  padding: 2rem 3.2rem;
}
.band-inner :deep(h1) {
  color: #fff;
  font-weight: 700;
  text-transform: uppercase;
  font-size: 1.9rem;
  margin: 0 0 0.4rem 0;
}
.band-inner :deep(p) {
  color: #b4c3da;
  font-size: 1.1rem;
  margin: 0;
}
</style>
