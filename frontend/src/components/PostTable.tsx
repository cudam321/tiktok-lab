import type { PostMetric } from "@/lib/api";
import { Eye, Heart, MessageCircle, Share2 } from "lucide-react";

interface PostTableProps {
  posts: PostMetric[];
  loading?: boolean;
}

export default function PostTable({ posts, loading }: PostTableProps) {
  if (loading) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center text-gray-500">
        Loading posts...
      </div>
    );
  }

  if (posts.length === 0) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center text-gray-500">
        No published posts yet
      </div>
    );
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800 text-left text-gray-500">
            <th className="px-4 py-3 font-medium">Post</th>
            <th className="px-4 py-3 font-medium text-right">
              <span className="flex items-center justify-end gap-1">
                <Eye size={14} /> Views
              </span>
            </th>
            <th className="px-4 py-3 font-medium text-right">
              <span className="flex items-center justify-end gap-1">
                <Heart size={14} /> Likes
              </span>
            </th>
            <th className="px-4 py-3 font-medium text-right">
              <span className="flex items-center justify-end gap-1">
                <MessageCircle size={14} /> Comments
              </span>
            </th>
            <th className="px-4 py-3 font-medium text-right">
              <span className="flex items-center justify-end gap-1">
                <Share2 size={14} /> Shares
              </span>
            </th>
            <th className="px-4 py-3 font-medium text-right">Engagement</th>
          </tr>
        </thead>
        <tbody>
          {posts.map((post) => (
            <tr
              key={post.post_id}
              className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors"
            >
              <td className="px-4 py-3">
                <div className="max-w-xs truncate text-white">
                  {post.caption || "Untitled"}
                </div>
                {post.published_at && (
                  <div className="text-xs text-gray-500 mt-0.5">
                    {new Date(post.published_at).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                      hour: "numeric",
                      minute: "2-digit",
                    })}
                  </div>
                )}
              </td>
              <td className="px-4 py-3 text-right text-white tabular-nums">
                {post.views.toLocaleString()}
              </td>
              <td className="px-4 py-3 text-right text-white tabular-nums">
                {post.likes.toLocaleString()}
              </td>
              <td className="px-4 py-3 text-right text-white tabular-nums">
                {post.comments.toLocaleString()}
              </td>
              <td className="px-4 py-3 text-right text-white tabular-nums">
                {post.shares.toLocaleString()}
              </td>
              <td className="px-4 py-3 text-right">
                <span
                  className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                    post.engagement_rate >= 5
                      ? "bg-emerald-400/10 text-emerald-400"
                      : post.engagement_rate >= 2
                      ? "bg-yellow-400/10 text-yellow-400"
                      : "bg-gray-800 text-gray-400"
                  }`}
                >
                  {post.engagement_rate.toFixed(1)}%
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
