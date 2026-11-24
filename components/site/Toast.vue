<script setup lang="ts">
const { msg } = useToastState()
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition duration-200"
      enter-from-class="opacity-0 translate-y-2"
      leave-active-class="transition duration-200"
      leave-to-class="opacity-0 translate-y-2"
    >
      <div
        v-if="msg"
        class="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-inverse text-white text-sm font-semibold px-5 py-3 rounded-xl shadow-pop"
        role="status"
      >{{ msg.text }}</div>
    </Transition>
  </Teleport>
</template>
