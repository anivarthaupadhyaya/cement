import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { useLocation, useNavigate } from 'react-router-dom'
import { z } from 'zod'

import { api } from '../api/client'
import type { User } from '../api/types'
import { Button, ErrorText, Field, Input } from '../components/ui'

const schema = z.object({
  username: z.string().min(1, 'Enter your username'),
  password: z.string().min(1, 'Enter your password'),
})
type Form = z.infer<typeof schema>

export function LoginPage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: { pathname: string } } | null)?.from?.pathname ?? '/'

  const { register, handleSubmit, formState } = useForm<Form>({ resolver: zodResolver(schema) })
  const login = useMutation({
    mutationFn: (body: Form) => api.post<User>('/api/auth/login', body),
    onSuccess: (user) => {
      qc.setQueryData(['me'], user)
      navigate(from, { replace: true })
    },
  })

  return (
    <div className="flex min-h-screen items-center justify-center bg-stone-100 p-4">
      <form
        onSubmit={handleSubmit((v) => login.mutate(v))}
        className="w-full max-w-sm space-y-4 rounded-xl border border-stone-200 bg-white p-6 shadow-sm"
      >
        <div>
          <h1 className="text-xl font-bold text-brand-700">Cement ERP</h1>
          <p className="text-sm text-stone-500">Sign in to continue</p>
        </div>
        <Field label="Username" error={formState.errors.username?.message}>
          <Input autoFocus autoComplete="username" {...register('username')} />
        </Field>
        <Field label="Password" error={formState.errors.password?.message}>
          <Input type="password" autoComplete="current-password" {...register('password')} />
        </Field>
        <ErrorText error={login.error} />
        <Button type="submit" className="w-full" disabled={login.isPending}>
          {login.isPending ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>
    </div>
  )
}
