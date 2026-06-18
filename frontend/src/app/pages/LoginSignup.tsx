import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { motion } from 'motion/react';
import { Brain, Mail, Lock, User, Phone, Briefcase, UserCircle, ShieldCheck } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { useAuth, UserRole } from '../context/AuthContext';
import { toast } from 'sonner';
import { InputOTP, InputOTPGroup, InputOTPSlot } from '../components/ui/input-otp';

export default function LoginSignup() {
  const navigate = useNavigate();
  const {
    login,
    signup,
    verifyEmailOtp,
    resendEmailOtp,
    isAuthenticated,
    user,
  } = useAuth();
  const [isLoading, setIsLoading] = useState(false);

  // Login state
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');

  // Signup state
  const [signupEmail, setSignupEmail] = useState('');
  const [signupPassword, setSignupPassword] = useState('');
  const [signupName, setSignupName] = useState('');
  const [signupPhone, setSignupPhone] = useState('');
  const [signupRole, setSignupRole] = useState<UserRole>('jobseeker');
  const [signupSubmitted, setSignupSubmitted] = useState(false);
  const [showOtpStep, setShowOtpStep] = useState(false);
  const [otpCode, setOtpCode] = useState('');
  const [pendingVerificationEmail, setPendingVerificationEmail] = useState('');
  const [pendingVerificationPassword, setPendingVerificationPassword] = useState('');
  const RESEND_OTP_SECONDS = 60;
  const [resendSeconds, setResendSeconds] = useState(0);

  const isSignupFieldEmpty = (value: string) => value.trim() === '';

  const isValidPassword = (password: string) => {
    return /^(?=.*[A-Za-z])(?=.*\d).{8,}$/.test(password);
  };

  const getSignupInputClass = (hasError: boolean) =>
    `pl-10 ${hasError ? 'border-red-500 focus-visible:ring-red-500' : ''}`;

  const isValidPhoneNumber = (phone: string) => {
    const cleanedPhone = phone.replace(/[\s()-]/g, '');
    return /^(03\d{9}|\+923\d{9}|923\d{9})$/.test(cleanedPhone);
  };

  useEffect(() => {
    if (isAuthenticated && user) {
      navigate(user.role === 'jobseeker' ? '/dashboard' : '/employer-dashboard', {
        replace: true,
      });
    }
  }, [isAuthenticated, user, navigate]);

  useEffect(() => {
    if (!showOtpStep || resendSeconds <= 0) return;

    const timer = setInterval(() => {
      setResendSeconds((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          return 0;
        }

        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [showOtpStep, resendSeconds]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      const loggedInUser = await login(loginEmail, loginPassword);
      toast.success('Login successful!');
      navigate(loggedInUser.role === 'jobseeker' ? '/dashboard' : '/employer-dashboard');
    } catch (error) {
      const typedError = error as Error & {
        emailNotVerified?: boolean;
        email?: string;
      };

      if (typedError.emailNotVerified) {
        setPendingVerificationEmail(typedError.email || loginEmail);
        setPendingVerificationPassword(loginPassword);
        setOtpCode('');
        setShowOtpStep(true);

        try {
          await resendEmailOtp(typedError.email || loginEmail);
          setResendSeconds(RESEND_OTP_SECONDS);
          toast.error('Please verify your email first. A new OTP has been sent.');
        } catch {
          setResendSeconds(RESEND_OTP_SECONDS);
          toast.error('Please verify your email first.');
        }

        return;
      }

      toast.error(error instanceof Error ? error.message || 'Login failed' : 'Login failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    setSignupSubmitted(true);

    const hasEmptyRequiredFields =
      isSignupFieldEmpty(signupName) ||
      isSignupFieldEmpty(signupEmail) ||
      isSignupFieldEmpty(signupPhone) ||
      isSignupFieldEmpty(signupPassword);

    if (hasEmptyRequiredFields) {
      toast.error('Please fill all required fields.');
      return;
    }

    if (!isValidPassword(signupPassword)) {
      toast.error('Password must be at least 8 characters and include at least 1 letter and 1 number.');
      return;
    }

    if (!isValidPhoneNumber(signupPhone)) {
      toast.error('Please enter a valid phone number, e.g. 03001234567 or +923001234567');
      return;
    }

    setIsLoading(true);
    try {
      await signup(signupEmail, signupPassword, signupName, signupPhone, signupRole);

      setPendingVerificationEmail(signupEmail);
      setPendingVerificationPassword(signupPassword);
      setOtpCode('');
      setShowOtpStep(true);
      setResendSeconds(RESEND_OTP_SECONDS);

      toast.success('Account created! Please check your email for the OTP.');
    } catch (error) {
      toast.error(error instanceof Error ? error.message || 'Signup failed' : 'Signup failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();

    if (otpCode.length !== 6) {
      toast.error('Please enter the 6-digit OTP.');
      return;
    }

    setIsLoading(true);

    try {
      const verifiedUser = await verifyEmailOtp(
        pendingVerificationEmail,
        otpCode,
        pendingVerificationPassword
      );

      toast.success('Email verified successfully!');
      navigate(verifiedUser.role === 'jobseeker' ? '/dashboard' : '/employer-dashboard');
    } catch (error) {
      toast.error(error instanceof Error ? error.message || 'OTP verification failed' : 'OTP verification failed');
    } finally {
      setIsLoading(false);
    }
  };


  const handleResendOtp = async () => {
    if (resendSeconds > 0) return;

    if (!pendingVerificationEmail) {
      toast.error('Email is missing. Please sign up again.');
      return;
    }

    setIsLoading(true);

    try {
      await resendEmailOtp(pendingVerificationEmail);
      setOtpCode('');
      setResendSeconds(RESEND_OTP_SECONDS);
      toast.success('A new OTP has been sent.');
    } catch (error) {
      toast.error(error instanceof Error ? error.message || 'Could not resend OTP' : 'Could not resend OTP');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50 flex items-center justify-center p-4">
      <div className="w-full max-w-6xl grid md:grid-cols-2 gap-8 items-center">
        {/* Left Side - Branding */}
        <motion.div
          initial={{ opacity: 0, x: -50 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.6 }}
          className="hidden md:block"
        >
          <div className="space-y-6">
            <div className="flex items-center gap-3">
              <div className="w-16 h-16 bg-gradient-to-br from-blue-600 to-purple-600 rounded-2xl flex items-center justify-center">
                <Brain className="w-10 h-10 text-white" />
              </div>
              <div>
                <h1 className="text-4xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
                  IntervAI Coach with Career Crafting
                </h1>
                <p className="text-gray-600">Powered by Artificial Intelligence</p>
              </div>
            </div>

            <div className="space-y-4 mt-12">
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
                className="flex items-start gap-4 p-4 bg-white rounded-xl shadow-sm"
              >
                <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
                  <Brain className="w-6 h-6 text-blue-600" />
                </div>
                <div>
                  <h3 className="font-semibold text-gray-900">AI Powered Resume Analysis</h3>
                  <p className="text-sm text-gray-600">Get instant feedback and improve your resume with AI suggestions</p>
                </div>
              </motion.div>

              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 }}
                className="flex items-start gap-4 p-4 bg-white rounded-xl shadow-sm"
              >
                <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center flex-shrink-0">
                  <Briefcase className="w-6 h-6 text-purple-600" />
                </div>
                <div>
                  <h3 className="font-semibold text-gray-900">Smart Interview Practice</h3>
                  <p className="text-sm text-gray-600">Practice with AI interviewer and get real-time feedback</p>
                </div>
              </motion.div>

              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4 }}
                className="flex items-start gap-4 p-4 bg-white rounded-xl shadow-sm"
              >
                <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center flex-shrink-0">
                  <UserCircle className="w-6 h-6 text-green-600" />
                </div>
                <div>
                  <h3 className="font-semibold text-gray-900">Profile Showcase</h3>
                  <p className="text-sm text-gray-600">Get discovered by top employers with your verified profile</p>
                </div>
              </motion.div>
            </div>
          </div>
        </motion.div>

        {/* Right Side - Login/Signup Forms */}
        <motion.div
          initial={{ opacity: 0, x: 50 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.6 }}
        >
          <Card className="shadow-2xl border-0 min-h-[500px]">
            <CardHeader className="pt-10 pb-8">
              <CardTitle className="text-2xl">Welcome</CardTitle>
              <CardDescription>Login or create an account to get started</CardDescription>
            </CardHeader>
            <CardContent className="px-6 pb-6">
              {showOtpStep ? (
                <form onSubmit={handleVerifyOtp} className="space-y-6">
                  <div className="text-center space-y-2">
                    <div className="mx-auto w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center">
                      <ShieldCheck className="w-6 h-6 text-blue-600" />
                    </div>

                    <h3 className="text-lg font-semibold">Verify your email</h3>

                    <p className="text-sm text-gray-600">
                      Enter the 6-digit OTP sent to{' '}
                      <span className="font-medium">{pendingVerificationEmail}</span>
                    </p>
                  </div>

                  <div className="flex justify-center">
                    <InputOTP maxLength={6} value={otpCode} onChange={setOtpCode}>
                      <InputOTPGroup>
                        <InputOTPSlot index={0} />
                        <InputOTPSlot index={1} />
                        <InputOTPSlot index={2} />
                        <InputOTPSlot index={3} />
                        <InputOTPSlot index={4} />
                        <InputOTPSlot index={5} />
                      </InputOTPGroup>
                    </InputOTP>
                  </div>

                  <Button type="submit" className="w-full" disabled={isLoading}>
                    {isLoading ? 'Verifying...' : 'Verify Email'}
                  </Button>

                  <Button
                    type="button"
                    variant="outline"
                    className="w-full"
                    onClick={handleResendOtp}
                    disabled={isLoading || resendSeconds > 0}
                  >
                    {resendSeconds > 0 ? `Resend OTP in ${resendSeconds}s` : 'Resend OTP'}
                  </Button>

                  <Button
                    type="button"
                    variant="link"
                    className="w-full"
                    onClick={() => {
                      setShowOtpStep(false);
                      setOtpCode('');
                      setResendSeconds(0);
                    }}
                    disabled={isLoading}
                  >
                    Back to login/signup
                  </Button>
                </form>
              ) : (
                <Tabs defaultValue="login" className="w-full">
                  <TabsList className="grid w-full grid-cols-2 mb-8">
                    <TabsTrigger value="login">Login</TabsTrigger>
                    <TabsTrigger value="signup">Sign Up</TabsTrigger>
                  </TabsList>

                  {/* Login Tab */}
                  <TabsContent value="login">
                    <form onSubmit={handleLogin} className="space-y-8">
                      <div className="space-y-2">
                        <Label htmlFor="login-email">Email</Label>
                        <div className="relative">
                          <Mail className="absolute left-3 top-3 h-4 w-4 text-gray-400" />
                          <Input
                            id="login-email"
                            type="email"
                            placeholder="example@gmail.com"
                            className="pl-10"
                            value={loginEmail}
                            onChange={(e) => setLoginEmail(e.target.value)}
                            required
                          />
                        </div>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="login-password">Password</Label>
                        <div className="relative">
                          <Lock className="absolute left-3 top-3 h-4 w-4 text-gray-400" />
                          <Input
                            id="login-password"
                            type="password"
                            placeholder="••••••••"
                            className="pl-10"
                            value={loginPassword}
                            onChange={(e) => setLoginPassword(e.target.value)}
                            required
                          />
                        </div>
                      </div>

                      <Button type="submit" className="w-full" disabled={isLoading}>
                        {isLoading ? 'Logging in...' : 'Login'}
                      </Button>
                    </form>
                  </TabsContent>

                  {/* Signup Tab */}
                  <TabsContent value="signup">
                    <form onSubmit={handleSignup} className="space-y-4" noValidate>
                      <div className="space-y-2">
                        <Label htmlFor="signup-name">
                          Full Name <span className="text-red-500">*</span>
                        </Label>
                        <div className="relative">
                          <User className="absolute left-3 top-3 h-4 w-4 text-gray-400" />
                          <Input
                            id="signup-name"
                            type="text"
                            placeholder="Ali Saleem"
                            className={getSignupInputClass(signupSubmitted && isSignupFieldEmpty(signupName))}
                            value={signupName}
                            onChange={(e) => setSignupName(e.target.value)}
                            required
                          />
                          {signupSubmitted && isSignupFieldEmpty(signupName) && (
                            <p className="text-sm text-red-500 mt-1">Full name is required.</p>
                          )}
                        </div>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="signup-email">
                          Email <span className="text-red-500">*</span>
                        </Label>
                        <div className="relative">
                          <Mail className="absolute left-3 top-3 h-4 w-4 text-gray-400" />
                          <Input
                            id="signup-email"
                            type="email"
                            placeholder="your.email@example.com"
                            className={getSignupInputClass(signupSubmitted && isSignupFieldEmpty(signupEmail))}
                            value={signupEmail}
                            onChange={(e) => setSignupEmail(e.target.value)}
                            required
                          />
                        </div>
                        {signupSubmitted && isSignupFieldEmpty(signupEmail) && (
                          <p className="text-sm text-red-500 mt-1">Email is required.</p>
                        )}
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="signup-phone">
                          Phone Number <span className="text-red-500">*</span>
                        </Label>
                        <div className="relative">
                          <Phone className="absolute left-3 top-3 h-4 w-4 text-gray-400" />
                          <Input
                            id="signup-phone"
                            type="tel"
                            placeholder="+923001234567"
                            className={getSignupInputClass(signupSubmitted && isSignupFieldEmpty(signupPhone))}
                            value={signupPhone}
                            onChange={(e) => setSignupPhone(e.target.value)}
                            maxLength={14}
                            required
                          />
                        </div>
                        {signupSubmitted && isSignupFieldEmpty(signupPhone) && (
                          <p className="text-sm text-red-500 mt-1">Phone number is required.</p>
                        )}
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="signup-password">
                          Password <span className="text-red-500">*</span>
                        </Label>
                        <div className="relative">
                          <Lock className="absolute left-3 top-3 h-4 w-4 text-gray-400" />
                          <Input
                            id="signup-password"
                            type="password"
                            placeholder="••••••••"
                            className={getSignupInputClass(
                              signupSubmitted &&
                              (isSignupFieldEmpty(signupPassword) || !isValidPassword(signupPassword))
                            )}
                            value={signupPassword}
                            onChange={(e) => setSignupPassword(e.target.value)}
                            required
                          />
                        </div>

                        {signupSubmitted && isSignupFieldEmpty(signupPassword) && (
                          <p className="text-sm text-red-500 mt-1">Password is required.</p>
                        )}

                        {signupSubmitted && !isSignupFieldEmpty(signupPassword) && !isValidPassword(signupPassword) && (
                          <p className="text-sm text-red-500 mt-1">
                            Password must be at least 8 characters and include at least 1 letter and 1 number.
                          </p>
                        )}
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="signup-role">I am a</Label>
                        <select
                          id="signup-role"
                          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                          value={signupRole}
                          onChange={(e) => setSignupRole(e.target.value as UserRole)}
                        >
                          <option value="jobseeker">Job Seeker</option>
                          <option value="employer">Employer</option>
                        </select>
                      </div>

                      <Button type="submit" className="w-full" disabled={isLoading}>
                        {isLoading ? 'Creating Account...' : 'Sign Up'}
                      </Button>
                    </form>
                  </TabsContent>
                </Tabs>
              )}
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}
