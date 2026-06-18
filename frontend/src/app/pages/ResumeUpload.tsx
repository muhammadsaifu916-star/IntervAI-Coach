import React, { useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { motion } from 'motion/react';
import { Upload, FileText, CheckCircle2, AlertCircle, ArrowLeft, Loader2 } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogFooter,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogAction,
  AlertDialogCancel,
} from '../components/ui/alert-dialog';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';
import { API_BASE_URL } from '../config';

const JOB_ROLES = [
  'AI Engineer',
  'Backend Developer',
  'Blockchain Developer',
  'Business Analyst',
  'Cloud Engineer',
  'Cybersecurity Analyst',
  'Data Scientist',
  'Database Administrator',
  'DevOps Engineer',
  'Frontend Developer',
  'Full Stack Developer',
  'Java Developer',
  'Machine Learning Engineer',
  'Mobile App Developer',
  'Python Developer',
  'QA Engineer',
  'React Developer',
  'Security Engineer',
  'Software Developer',
  'SQL Developer',
  'UI/UX Developer',
];

export default function ResumeUpload() {
  const navigate = useNavigate();
  const { updateProfile, authFetch, refreshUser, profile } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [jobRole, setJobRole] = useState('');
  const [yearsExperience, setYearsExperience] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const [showWarning, setShowWarning] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // A re-upload wipes quiz/interview progress. Only warn if there's progress to lose.
  const hasProgress =
    (profile?.quiz_attempts ?? 0) > 0 || (profile?.interview_attempts ?? 0) > 0;

  const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB

  const validateAndSetFile = (selectedFile: File) => {
    const isPdf =
      selectedFile.type === 'application/pdf' &&
      selectedFile.name.toLowerCase().endsWith('.pdf');

    if (!isPdf) {
      toast.error('Please upload PDF file only');
      return;
    }

    if (selectedFile.size > MAX_FILE_SIZE) {
      toast.error('File must be under 10MB');
      return;
    }

    setFile(selectedFile);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      validateAndSetFile(selectedFile);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      validateAndSetFile(droppedFile);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !jobRole || !yearsExperience) {
      toast.error('Please fill all fields');
      return;
    }
    // Re-upload is destructive — confirm first if there's progress to lose.
    if (hasProgress) {
      setShowWarning(true);
      return;
    }
    doUpload();
  };

  const doUpload = async () => {
    if (!file || !jobRole || !yearsExperience) return;

    setIsUploading(true);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('job_role', jobRole);
      formData.append('years_experience', yearsExperience);

      const response = await authFetch(`${API_BASE_URL}/api/resumes/upload/`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);

        const title =
          errorData?.error ||
          'Resume upload failed';

        const description =
          errorData?.details ||
          errorData?.reason ||
          errorData?.detail ||
          errorData?.message ||
          'Something went wrong while analyzing your resume.';

        toast.error(title, {
          description,
        });

        return;
      }

      const data = await response.json();
      // The upload endpoint returns the full analysis:
      // { resume_id, score, feedback, grade, detected_role, analysis_log,
      //   target_role, selected_role, role_alignment, role_penalty,
      //   role_mismatch_block, role_match_message, strengths, weaknesses,
      //   improvement_plan, quality_analysis, grammar_issues,
      //   missing_sections, quiz_unlocked, progress_cleared }

      const experience = parseFloat(yearsExperience);
      let tier = 'Entry Level';
      if (experience > 1 && experience <= 3) tier = 'Mid Level';
      else if (experience > 3) tier = 'Senior Level';

      updateProfile({
        job_role: jobRole,
        years_experience: experience,
        experience_tier: tier,
        resume_score: data.score,
        resume_feedback: data.feedback,
        resume_quiz_unlocked: data.quiz_unlocked,
      });

      await refreshUser();

      toast.success(
        data.progress_cleared
          ? 'Resume uploaded. Your previous quiz and interview were cleared — you’ll need to retake them.'
          : 'Resume uploaded and analysed!'
      );
      // Pass the FULL API response to the feedback page via router state so
      // the detailed analysis (scores, strengths, plan, role match, etc.)
      // is available. Previously only {score, feedback, quiz_unlocked} were
      // passed, which made the feedback page render empty/0% sections.
      navigate('/resume-feedback', {
        state: data,
      });
    } catch {
      toast.error('Resume upload failed', {
        description: 'Please check your file and try again.',
      });
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      <AlertDialog open={showWarning} onOpenChange={setShowWarning}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Re-uploading will erase your progress</AlertDialogTitle>
            <AlertDialogDescription>
              Your previous quiz and interview results will be permanently deleted, and your
              published profile will be unpublished. Any active retry cooldown still applies.
              This can’t be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isUploading}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setShowWarning(false);
                doUpload();
              }}
            >
              Delete &amp; re-upload
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-50 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" onClick={() => navigate('/dashboard')}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Dashboard
            </Button>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-blue-600 to-purple-600 rounded-lg flex items-center justify-center">
                <FileText className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-gray-900">Resume Upload</h1>
                <p className="text-sm text-gray-600">Step 1 of 4</p>
              </div>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <Card className="border-0 shadow-2xl">
            <CardHeader>
              <CardTitle className="text-2xl">Upload Your Resume</CardTitle>
              <CardDescription>
                Upload your resume in PDF format. Our AI will analyze it and provide feedback.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-6">
                {/* Job Role */}
                <div className="space-y-2">
                  <Label htmlFor="job-role">Desired Job Role</Label>
                  <Select value={jobRole} onValueChange={setJobRole} required>
                    <SelectTrigger id="job-role">
                      <SelectValue placeholder="Select a job role" />
                    </SelectTrigger>
                    <SelectContent>
                      {JOB_ROLES.map((role) => (
                        <SelectItem key={role} value={role}>{role}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Years of Experience */}
                <div className="space-y-2">
                  <Label htmlFor="experience">Years of Experience</Label>
                  <Select value={yearsExperience} onValueChange={setYearsExperience} required>
                    <SelectTrigger id="experience">
                      <SelectValue placeholder="Select years of experience" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="1">0 to 3 years (Entry Level)</SelectItem>
                      <SelectItem value="3">3+ to 6 years (Mid Level)</SelectItem>
                      <SelectItem value="5">6+ years (Senior Level)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* File Upload */}
                <div className="space-y-2">
                  <Label>Resume (PDF only)</Label>
                  <div
                    className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${isDragOver
                      ? 'border-blue-500 bg-blue-50'
                      : file
                        ? 'border-green-500 bg-green-50'
                        : 'border-gray-300 hover:border-gray-400'
                      }`}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                  >
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".pdf,application/pdf"
                      onChange={handleFileChange}
                      className="hidden"
                      id="file-upload"
                    />

                    {file ? (
                      <div className="space-y-2">
                        <CheckCircle2 className="w-12 h-12 text-green-600 mx-auto" />
                        <p className="text-lg font-medium text-green-700">{file.name}</p>
                        <p className="text-sm text-gray-600">
                          {(file.size / 1024).toFixed(2)} KB
                        </p>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => fileInputRef.current?.click()}
                        >
                          Change File
                        </Button>
                      </div>
                    ) : (
                      <label htmlFor="file-upload" className="cursor-pointer block">
                        <div className="space-y-2">
                          <Upload className="w-12 h-12 text-gray-400 mx-auto" />
                          <p className="text-lg font-medium text-gray-700">
                            Drop your PDF here or click to browse
                          </p>
                          <p className="text-sm text-gray-500">Maximum file size: 10MB</p>
                        </div>
                      </label>
                    )}
                  </div>
                </div>

                {/* Info Box */}
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
                  <div className="text-sm text-blue-800">
                    <p className="font-medium mb-1">What our AI checks:</p>
                    <ul className="list-disc list-inside space-y-1 text-blue-700">
                      <li>Grammar, spelling, and punctuation</li>
                      <li>Formatting and layout consistency</li>
                      <li>Use of action verbs and keywords</li>
                      <li>Overall structure and length</li>
                      <li>Relevance to your target role</li>
                    </ul>
                  </div>
                </div>

                {/* Submit Button */}
                <Button
                  type="submit"
                  className="w-full"
                  size="lg"
                  disabled={isUploading || !file || !jobRole || !yearsExperience}
                >
                  {isUploading ? (
                    <>
                      <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                      Analyzing Resume...
                    </>
                  ) : (
                    <>
                      <Upload className="w-5 h-5 mr-2" />
                      Upload & Analyze Resume
                    </>
                  )}
                </Button>
              </form>
            </CardContent>
          </Card>

          {/* Benefits Section */}
          <div className="grid md:grid-cols-3 gap-6 mt-8">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="bg-white p-6 rounded-lg shadow-md"
            >
              <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center mb-4">
                <CheckCircle2 className="w-6 h-6 text-blue-600" />
              </div>
              <h3 className="font-semibold text-gray-900 mb-2">Instant Analysis</h3>
              <p className="text-sm text-gray-600">
                Get immediate AI-powered feedback on your resume's strengths and weaknesses
              </p>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="bg-white p-6 rounded-lg shadow-md"
            >
              <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center mb-4">
                <FileText className="w-6 h-6 text-purple-600" />
              </div>
              <h3 className="font-semibold text-gray-900 mb-2">Template Suggestions</h3>
              <p className="text-sm text-gray-600">
                Choose from 4 professionally designed templates to improve your resume
              </p>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4 }}
              className="bg-white p-6 rounded-lg shadow-md"
            >
              <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center mb-4">
                <AlertCircle className="w-6 h-6 text-green-600" />
              </div>
              <h3 className="font-semibold text-gray-900 mb-2">Score & Grade</h3>
              <p className="text-sm text-gray-600">
                Receive a grade (Weak/Satisfactory/Good/Excellent) based on multiple criteria
              </p>
            </motion.div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}