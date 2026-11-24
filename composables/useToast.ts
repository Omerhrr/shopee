/** Tiny toast store. Callable: const toast = useToastState(); toast('Saved'). */
import type { Ref } from 'vue'

interface ToastMsg {
  text: string
  id: number
}

export function useToastState(): ((text: string) => void) & { msg: Ref<ToastMsg | null> } {
  const msg = useState<ToastMsg | null>('toast', () => null)
  const show = (text: string) => {
    const id = Date.now()
    msg.value = { text, id }
    setTimeout(() => {
      if (msg.value?.id === id) msg.value = null
    }, 2200)
  }
  return Object.assign(show, { msg }) as any
}
