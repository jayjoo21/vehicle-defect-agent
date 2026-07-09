import { useState } from 'react'

export interface MyCar {
  model: string
  year: string
}

const STORAGE_KEY = 'mobiscope:my-car'

export function loadMyCar(): MyCar | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as MyCar) : null
  } catch {
    return null
  }
}

function saveMyCar(car: MyCar) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(car))
}

function clearMyCar() {
  localStorage.removeItem(STORAGE_KEY)
}

export function useMyCar() {
  const [car, setCar] = useState<MyCar | null>(() => loadMyCar())

  function register(next: MyCar) {
    saveMyCar(next)
    setCar(next)
  }

  function reset() {
    clearMyCar()
    setCar(null)
  }

  return { car, register, reset }
}
